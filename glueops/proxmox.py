"""Async client for the Proxmox VE REST API.

Covers the VM-provisioning surface shared by GlueOps services (tools-api,
provisioner): task polling, image caching via download-url, cloud-init NoCloud
ISO upload, VM lifecycle, native-tag discovery, and guest-agent queries.

Requires Proxmox VE 8.4+ when using ensure_image_cached (qcow2 via the
"import" content type of download-url).

Usage:
    from glueops.proxmox import ProxmoxClient, build_cloudinit_iso

    client = ProxmoxClient(
        host="pve.example.com",
        token_id="automation@pve!mytoken",
        token_secret="...",
        storage="local-zfs",
    )
    vms = await client.list_vms_by_tags(["my-app", "my-tenant"])
"""

import asyncio
import base64
import io
import ipaddress
import os
import re
import urllib.parse

import httpx
import pycdlib

from glueops import setup_logging

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
logger = setup_logging.configure(level=LOG_LEVEL)


def build_cloudinit_iso(user_data: bytes, meta_data: bytes) -> bytes:
    """Build a cloud-init NoCloud (cidata) ISO from user-data and meta-data."""
    iso = pycdlib.PyCdlib()
    iso.new(vol_ident="cidata", rock_ridge="1.09")
    iso.add_fp(io.BytesIO(user_data), length=len(user_data), iso_path="/USERDATA;1", rr_name="user-data")
    iso.add_fp(io.BytesIO(meta_data), length=len(meta_data), iso_path="/METADATA;1", rr_name="meta-data")
    buf = io.BytesIO()
    iso.write_fp(buf)
    iso.close()
    return buf.getvalue()


def _decode_agent_output(data: str) -> str:
    # QGA returns out-data/err-data base64-encoded; PVE passes them through undecoded
    try:
        return base64.b64decode(data).decode(errors="replace")
    except (ValueError, TypeError):
        return data


class ProxmoxClient:
    """
    Async client for one Proxmox VE cluster, authenticated with an API token.

    :param host: Proxmox host or VIP (no scheme).
    :param token_id: API token id, e.g. "automation@pve!mytoken".
    :param token_secret: API token secret.
    :param storage: Storage id used for VM disks, cloud-init ISOs, and cached images.
    :param port: API port (default 8006).
    :param verify_ssl: Verify the API TLS certificate (default True).
    :param download_server_url: Base URL hosting <image>.qcow2 files; required
        only for ensure_image_cached. Note the PVE node performs the fetch.
    :param download_timeout: Seconds to wait for image downloads (default 1800).
    """

    def __init__(self, host, token_id, token_secret, storage, port=8006,
                 verify_ssl=True, download_server_url=None, download_timeout=1800.0):
        self.host = host
        self.port = port
        self.storage = storage
        self.verify_ssl = verify_ssl
        self.download_server_url = download_server_url
        self.download_timeout = download_timeout
        self._token_id = token_id
        self._token_secret = token_secret
        self._http = None
        if not verify_ssl:
            logger.warning(f"SSL verification disabled for Proxmox host {host}")

    # --- HTTP plumbing -----------------------------------------------------

    def _base(self) -> str:
        return f"https://{self.host}:{self.port}/api2/json"

    def _client(self) -> httpx.AsyncClient:
        if self._http is None or self._http.is_closed:
            headers = {"Authorization": f"PVEAPIToken={self._token_id}={self._token_secret}"}
            self._http = httpx.AsyncClient(verify=self.verify_ssl, timeout=60.0, headers=headers)
        return self._http

    @staticmethod
    def _check(response: httpx.Response):
        if response.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"Proxmox API {response.request.method} {response.request.url.path} "
                f"failed with {response.status_code}: {response.text}",
                request=response.request,
                response=response,
            )

    async def _get(self, path, **params):
        r = await self._client().get(f"{self._base()}{path}", params=params or None)
        self._check(r)
        return r.json()["data"]

    async def _post(self, path, data=None, files=None):
        r = await self._client().post(f"{self._base()}{path}", data=data, files=files)
        self._check(r)
        return r.json()["data"]

    async def _put(self, path, data):
        r = await self._client().put(f"{self._base()}{path}", data=data)
        self._check(r)
        return r.json()["data"]

    async def _delete(self, path, **params):
        r = await self._client().delete(f"{self._base()}{path}", params=params or None)
        self._check(r)
        return r.json()["data"]

    async def aclose(self):
        if self._http is not None and not self._http.is_closed:
            await self._http.aclose()

    # --- Tasks ---------------------------------------------------------------

    async def poll_task(self, upid: str, timeout: float = 600.0):
        """Wait for a Proxmox task (UPID) to finish; raise on failure or timeout.

        On timeout the task is best-effort stopped so an abandoned task (e.g. a
        wedged download-url holding its target file) doesn't block retries with 409s.
        """
        task_node = upid.split(":")[1]
        encoded = urllib.parse.quote(upid, safe="")
        deadline = asyncio.get_running_loop().time() + timeout
        while True:
            data = await self._get(f"/nodes/{task_node}/tasks/{encoded}/status")
            if data["status"] == "stopped":
                if data.get("exitstatus") != "OK":
                    raise RuntimeError(f"Proxmox task failed: {data}")
                return
            if asyncio.get_running_loop().time() >= deadline:
                try:
                    await self._delete(f"/nodes/{task_node}/tasks/{encoded}")
                    logger.warning(f"Stopped stalled Proxmox task {upid} after {timeout:.0f}s")
                except Exception as e:
                    logger.error(f"Failed to stop stalled Proxmox task {upid}: {e}")
                raise TimeoutError(f"Proxmox task {upid} still running after {timeout:.0f}s; check the task log in the Proxmox UI")
            await asyncio.sleep(3)

    # --- Images & ISOs ---------------------------------------------------------

    async def get_next_vmid(self) -> str:
        """Return the cluster's next free vmid. NOTE: non-reserving — a concurrent
        caller can claim the same id; retry VM creation on conflict."""
        return await self._get("/cluster/nextid")

    async def ensure_image_cached(self, node: str, image: str):
        """Download <image>.qcow2 from download_server_url onto the node's storage
        (content type "import") unless already present. Requires PVE 8.4+."""
        if not self.download_server_url:
            raise ValueError("download_server_url is required for ensure_image_cached")
        content = await self._get(f"/nodes/{node}/storage/{self.storage}/content", content="import")
        volid = f"{self.storage}:import/{image}.qcow2"
        if volid in {v["volid"] for v in (content or [])}:
            logger.info(f"Image {image} already cached on {node}")
            return
        logger.info(f"Downloading {image} to {node}")
        try:
            upid = await self._post(f"/nodes/{node}/storage/{self.storage}/download-url", data={
                "url": f"{self.download_server_url.rstrip('/')}/{image}.qcow2",
                "filename": f"{image}.qcow2",
                "content": "import",
            })
            await self.poll_task(upid, timeout=self.download_timeout)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 409:
                # Another download already in progress — wait for it to complete.
                # download-url renames a temp file on completion, so appearance in
                # the content listing means the download finished intact.
                deadline = asyncio.get_running_loop().time() + self.download_timeout
                logger.info(f"Image {image} download already in progress on {node}, waiting...")
                while asyncio.get_running_loop().time() < deadline:
                    await asyncio.sleep(5)
                    content = await self._get(f"/nodes/{node}/storage/{self.storage}/content", content="import")
                    if volid in {v["volid"] for v in (content or [])}:
                        return
                raise TimeoutError(
                    f"Timed out after {self.download_timeout:.0f}s waiting for {image} on {node}; the download "
                    f"started by another request may have stalled or failed — check that node's task log, then retry."
                )
            raise

    async def upload_iso(self, node: str, iso_filename: str, iso_bytes: bytes) -> str:
        """Upload ISO bytes to the node's storage. Overwrites any same-named file."""
        upid = await self._post(
            f"/nodes/{node}/storage/{self.storage}/upload",
            data={"content": "iso"},
            files={"filename": (iso_filename, io.BytesIO(iso_bytes), "application/octet-stream")},
        )
        await self.poll_task(upid)
        return iso_filename

    async def _delete_iso_volid(self, node: str, volid: str):
        result = await self._delete(f"/nodes/{node}/storage/{self.storage}/content/{urllib.parse.quote(volid, safe='')}")
        if isinstance(result, str) and result.startswith("UPID:"):
            await self.poll_task(result)

    async def eject_and_delete_iso(self, node: str, vmid: str, iso_filename: str):
        """Best-effort: detach the ide2 cdrom, then delete the ISO volume.

        If the eject fails (VM gone, guest-locked tray, hotplug disabled) the
        volume is NOT deleted: the VM config may still reference it (with
        onboot the next hypervisor boot would fail on the missing volume), and
        the same filename may meanwhile belong to a successor VM's fresh ISO.
        Leftovers are cleaned by delete_isos_matching, whose in-use check makes
        deletion safe."""
        try:
            await self.update_vm_config(node, vmid, ide2="none,media=cdrom")
        except Exception as e:
            logger.error(f"Failed to eject ISO from VM {vmid}: {e}; leaving {iso_filename} for the orphan sweep")
            return
        try:
            await self._delete_iso_volid(node, f"{self.storage}:iso/{iso_filename}")
        except Exception as e:
            logger.error(f"Failed to delete ISO {iso_filename}: {e}")

    @staticmethod
    def _collect_iso_volids(values, referenced: set):
        for value in values:
            if not isinstance(value, str) or ":iso/" not in value:
                continue
            for part in value.split(","):
                if ":iso/" in part:
                    referenced.add(part.split("=", 1)[-1].strip())

    async def referenced_iso_volids(self) -> set:
        """Return every iso volid referenced by any qemu VM cluster-wide: current
        config values, PENDING values (GET /config would return pending-applied
        values, hiding e.g. an ISO whose eject is still pending), and every
        snapshot's config (a snapshot rollback restores its ISO reference).

        Proxmox does not refcount iso content — deleting an attached ISO succeeds
        and breaks the VM — so this scan is the only 'in use' signal there is.

        Fails CLOSED: raises RuntimeError if any node is offline or any per-VM
        fetch fails, because an incomplete reference set must not authorize
        deletion (a shared-storage ISO could be referenced by an unreachable
        node's VM)."""
        referenced = set()
        nodes = await self.list_nodes()
        offline = [n["node"] for n in nodes if n.get("status") != "online"]
        if offline:
            raise RuntimeError(f"ISO reference scan incomplete: node(s) not online: {', '.join(offline)}")
        for n in nodes:
            node = n["node"]
            vms = await self.list_node_vms(node)
            for vm in vms or []:
                vmid = str(vm["vmid"])
                pending = await self._get(f"/nodes/{node}/qemu/{vmid}/pending")
                for entry in pending or []:
                    self._collect_iso_volids([entry.get("value"), entry.get("pending")], referenced)
                snapshots = await self._get(f"/nodes/{node}/qemu/{vmid}/snapshot")
                for snap in snapshots or []:
                    name = snap.get("name")
                    if not name or name == "current":
                        continue
                    snap_config = await self._get(f"/nodes/{node}/qemu/{vmid}/config", snapshot=name)
                    self._collect_iso_volids((snap_config or {}).values(), referenced)
        return referenced

    async def _storage_is_shared(self, node: str) -> bool:
        status = await self.get_storage_status(node)
        return bool(status.get("shared"))

    async def delete_isos_matching(self, filename_regex: str, skip_in_use: bool = True) -> int:
        """Best-effort deletion of ISO volumes whose filename matches the regex,
        swept across every node's storage (VM purge never removes standalone iso
        content, so orphan cleanup needs an explicit sweep). Returns count deleted.

        With skip_in_use (default), candidates still referenced by any VM config
        (current, pending, or snapshot) are skipped with a warning — Proxmox
        itself would delete them regardless. If the reference scan cannot be
        completed (offline node, failed fetch), NOTHING is deleted this sweep;
        orphans self-heal on a later sweep, wrongly deleted ISOs don't.

        On shared storage identical volids across nodes are one file (deduped);
        on local storage the same volid per node is a distinct file and each
        node's copy is deleted separately."""
        pattern = re.compile(rf"^{re.escape(self.storage)}:iso/(?:{filename_regex})$")
        shared = None
        seen = set()
        candidates = []
        for n in await self.list_nodes():
            node = n["node"]
            try:
                content = await self._get(f"/nodes/{node}/storage/{self.storage}/content", content="iso")
            except (httpx.HTTPStatusError, httpx.TransportError):
                continue  # storage not present/available on this node
            if shared is None:
                try:
                    shared = await self._storage_is_shared(node)
                except (httpx.HTTPStatusError, httpx.TransportError):
                    shared = False  # assume local: per-node deletion covers both cases
            for v in content or []:
                volid = v["volid"]
                key = volid if shared else (node, volid)
                if key in seen or not pattern.match(volid):
                    continue
                seen.add(key)
                candidates.append((node, volid))
        if not candidates:
            return 0
        if skip_in_use:
            try:
                referenced = await self.referenced_iso_volids()
            except Exception as e:
                logger.warning(f"Skipping ISO sweep ({len(candidates)} candidate(s)): {e}")
                return 0
        else:
            referenced = set()
        deleted = 0
        for node, volid in candidates:
            if volid in referenced:
                logger.warning(f"Skipping ISO {volid}: still referenced by a VM config, pending change, or snapshot")
                continue
            try:
                await self._delete_iso_volid(node, volid)
                deleted += 1
            except Exception as e:
                logger.error(f"Failed to delete ISO {volid}: {e}")
        return deleted

    # --- VM lifecycle ------------------------------------------------------------

    async def create_vm(self, node: str, vmid: str, vm_name: str, vcpus: int, memory_mb: int,
                        image: str, iso_filename: str, bridge: str, tags=None,
                        vlan_tag=None, onboot: bool = True, cpu: str = "x86-64-v2-AES",
                        description=None):
        """Create a VM importing its disk from the cached image, with a cloud-init
        ISO attached on ide2 and the QEMU guest agent enabled.

        :param tags: Optional native Proxmox tags (lowercased to match how PVE
            stores them, so later list_vms_by_tags matching agrees).
        :param description: Optional VM description/notes (e.g. for consumers that
            track managed VMs via encoded description instead of tags).
        """
        net0 = f"virtio,bridge={bridge}"
        if vlan_tag:
            net0 += f",tag={vlan_tag}"
        data = {
            "vmid": vmid,
            "name": vm_name,
            "memory": memory_mb,
            "cores": vcpus,
            "cpu": cpu,
            "ostype": "l26",
            "agent": "1",
            "onboot": 1 if onboot else 0,
            "virtio0": f"{self.storage}:0,import-from={self.storage}:import/{image}.qcow2,iothread=1,format=raw",
            "ide2": f"{self.storage}:iso/{iso_filename},media=cdrom",
            "boot": "order=virtio0",
            "net0": net0,
            "serial0": "socket",
        }
        if tags:
            data["tags"] = ";".join(t.lower() for t in tags)
        if description is not None:
            data["description"] = description
        upid = await self._post(f"/nodes/{node}/qemu", data=data)
        await self.poll_task(upid)

    async def resize_disk(self, node: str, vmid: str, disk_gb=None, disk_mb=None):
        """Grow the primary disk to an absolute size. Pass exactly one of disk_gb
        or disk_mb (MB granularity for consumers whose sizes aren't whole GB)."""
        if (disk_gb is None) == (disk_mb is None):
            raise ValueError("Pass exactly one of disk_gb or disk_mb")
        size = f"{disk_gb}G" if disk_gb is not None else f"{disk_mb}M"
        result = await self._put(f"/nodes/{node}/qemu/{vmid}/resize", data={"disk": "virtio0", "size": size})
        if isinstance(result, str) and result.startswith("UPID:"):
            await self.poll_task(result)

    async def start_vm(self, node: str, vmid: str):
        upid = await self._post(f"/nodes/{node}/qemu/{vmid}/status/start")
        await self.poll_task(upid)

    async def stop_vm(self, node: str, vmid: str):
        upid = await self._post(f"/nodes/{node}/qemu/{vmid}/status/stop")
        await self.poll_task(upid)

    @staticmethod
    def _is_missing_vm_error(e: Exception) -> bool:
        return isinstance(e, httpx.HTTPStatusError) and "does not exist" in e.response.text

    async def delete_vm(self, node: str, vmid: str):
        """Stop (if running) and destroy a VM. Idempotent: an already-deleted VM
        is treated as success (DELETE /qemu/{vmid} itself is not idempotent)."""
        try:
            status_data = await self._get(f"/nodes/{node}/qemu/{vmid}/status/current")
            if status_data.get("status") == "running":
                upid = await self._post(f"/nodes/{node}/qemu/{vmid}/status/stop")
                await self.poll_task(upid)
        except Exception as e:
            if self._is_missing_vm_error(e):
                logger.info(f"VM {vmid} on {node} already gone, nothing to delete")
                return
            logger.error(f"Failed to stop VM {vmid} before delete: {e}")
        try:
            upid = await self._delete(f"/nodes/{node}/qemu/{vmid}", purge=1)
            await self.poll_task(upid)
        except Exception as e:
            if self._is_missing_vm_error(e):
                logger.info(f"VM {vmid} on {node} already gone, nothing to delete")
                return
            raise

    async def get_vm_config(self, node: str, vmid: str) -> dict:
        """Return the VM's current config (name, description, tags, disks, ...)."""
        return await self._get(f"/nodes/{node}/qemu/{vmid}/config")

    async def update_vm_config(self, node: str, vmid: str, **fields):
        """Set arbitrary VM config fields, e.g. update_vm_config(node, vmid,
        description=..., onboot=1). Used by consumers that track managed VMs
        via an encoded description rather than native tags."""
        await self._put(f"/nodes/{node}/qemu/{vmid}/config", data=fields)

    async def list_nodes(self) -> list:
        """Return the cluster's nodes as reported by GET /nodes (includes status,
        maxcpu, maxmem, cpu, mem — the inputs for capacity accounting)."""
        return await self._get("/nodes") or []

    async def get_storage_status(self, node: str) -> dict:
        """Return this client's storage status on a node (avail/total/used bytes)."""
        return await self._get(f"/nodes/{node}/storage/{self.storage}/status")

    async def list_node_vms(self, node: str) -> list:
        """Return the qemu VMs on one node (includes per-VM cpus/maxmem/status)."""
        return await self._get(f"/nodes/{node}/qemu") or []

    async def list_vms_by_tags(self, required_tags: list) -> list:
        """Return [{node, vmid, name}] for every qemu VM carrying all required_tags."""
        resources = await self._get("/cluster/resources", type="vm")
        required = {t.lower() for t in required_tags}
        matches = []
        for r in resources or []:
            if r.get("type") != "qemu":
                continue
            # Proxmox accepts both ";" and "," as tag separators, and stores tags lowercased
            vm_tags = {t.lower() for t in re.split(r"[;,]", r.get("tags") or "")}
            if required.issubset(vm_tags):
                matches.append({"node": r["node"], "vmid": str(r["vmid"]), "name": r.get("name", "")})
        return matches

    # --- Guest agent ------------------------------------------------------------

    async def agent_exec(self, node: str, vmid: str, command: list, timeout: float = 180.0) -> str:
        """Run a command in the guest via the QEMU guest agent; return its output."""
        r = await self._client().post(
            f"{self._base()}/nodes/{node}/qemu/{vmid}/agent/exec",
            json={"command": command, "input-data": ""},
        )
        self._check(r)
        pid = r.json()["data"]["pid"]
        deadline = asyncio.get_running_loop().time() + timeout
        while asyncio.get_running_loop().time() < deadline:
            result = await self._get(f"/nodes/{node}/qemu/{vmid}/agent/exec-status", pid=pid)
            if result.get("exited"):
                if result.get("exitcode", 1) != 0:
                    raise RuntimeError(f"Command exited {result.get('exitcode')}: {_decode_agent_output(result.get('err-data', ''))!r}")
                return _decode_agent_output(result.get("out-data", "")) + _decode_agent_output(result.get("err-data", ""))
            await asyncio.sleep(3)
        raise TimeoutError(f"Command did not exit within {timeout:.0f}s")

    async def wait_for_cloud_init(self, node: str, vmid: str, agent_timeout: int = 300, cloudinit_timeout: int = 600):
        """Poll the guest agent until it responds, then poll for cloud-init completion.

        Raises if the agent never comes up; logs a warning (without raising) if
        cloud-init doesn't finish in time, since boot-finished may just be slow.
        """
        loop = asyncio.get_running_loop()
        agent_end = loop.time() + agent_timeout
        while loop.time() < agent_end:
            try:
                await self._get(f"/nodes/{node}/qemu/{vmid}/agent/info")
                logger.info(f"VM {vmid}: guest agent up, polling cloud-init status")
                break
            except (httpx.HTTPStatusError, httpx.TransportError):
                await asyncio.sleep(5)
        else:
            raise RuntimeError(f"VM {vmid}: guest agent not available after {agent_timeout}s")
        cloudinit_end = loop.time() + cloudinit_timeout
        while loop.time() < cloudinit_end:
            try:
                await self.agent_exec(node, vmid, ["ls", "/var/lib/cloud/instance/boot-finished"])
                logger.info(f"VM {vmid}: cloud-init complete")
                return
            except (RuntimeError, TimeoutError, httpx.HTTPStatusError, httpx.TransportError) as e:
                logger.debug(f"VM {vmid}: cloud-init not ready: {e}")
            await asyncio.sleep(5)
        logger.warning(f"VM {vmid}: cloud-init did not complete within {cloudinit_timeout}s, continuing anyway")

    async def get_vm_ipv4(self, node: str, vmid: str, timeout: int = 120,
                          skip_interface_prefixes=("lo", "docker", "br-", "veth")) -> str:
        """Ask the QEMU guest agent for the VM's primary IPv4 address.

        Guest-agent data is guest-controlled (including the ip-address-type field),
        so the address is parsed with ipaddress and only the normalized form is
        returned; loopback/link-local/unspecified addresses are skipped.
        """
        loop = asyncio.get_running_loop()
        end = loop.time() + timeout
        while loop.time() < end:
            try:
                data = await self._get(f"/nodes/{node}/qemu/{vmid}/agent/network-get-interfaces")
                for iface in data.get("result", []):
                    iface_name = iface.get("name", "")
                    if iface_name.startswith(tuple(skip_interface_prefixes)):
                        continue
                    for addr in iface.get("ip-addresses", []):
                        if addr.get("ip-address-type") != "ipv4":
                            continue
                        try:
                            ip = ipaddress.IPv4Address(addr.get("ip-address", ""))
                        except ValueError:
                            logger.warning(f"VM {vmid}: guest agent reported non-IPv4 string {addr.get('ip-address')!r}, skipping")
                            continue
                        if ip.is_loopback or ip.is_link_local or ip.is_unspecified:
                            continue
                        logger.info(f"VM {vmid}: found IPv4 {ip} on interface {iface_name}")
                        return str(ip)
            except (httpx.HTTPStatusError, httpx.TransportError) as e:
                logger.debug(f"VM {vmid}: guest agent network query not ready: {e}")
            await asyncio.sleep(5)
        raise RuntimeError(f"Could not determine IPv4 address for VM {vmid} within {timeout}s")
