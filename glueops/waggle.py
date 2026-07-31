"""Async client for the Waggle API (Proxmox placement oracle).

Waggle decides where VMs go but does not create them: create a pool against a
pre-existing datacenter and slot, read the resulting placements (one hypervisor
per VM), provision the VMs yourself, then backfill each Proxmox vmid onto its
placement. See https://github.com/glueops/waggle.

Usage:
    from glueops.waggle import WaggleClient

    waggle = WaggleClient("https://waggle.example.com", "wgl_...")
    datacenter = await waggle.get_datacenter_by_name("dc1")
    slot = await waggle.get_slot_by_name("2vcpu-4gb-40gb")
    pool = await waggle.create_pool(datacenter["id"], slot["id"], "my-pool", 3)
    placements = await waggle.get_pool_placements(pool["id"])
"""

import os

import httpx

from glueops import setup_logging

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
logger = setup_logging.configure(level=LOG_LEVEL)


class WaggleClient:
    """
    Async client for one Waggle organization, authenticated with an org API key.

    :param api_url: Base URL of the Waggle server; "/api/v1" is appended if missing.
    :param api_key: Organization API key ("wgl_..." prefix).
    """

    def __init__(self, api_url, api_key):
        base = api_url.rstrip("/")
        if not base.endswith("/api/v1"):
            base += "/api/v1"
        self.api_url = base
        self._api_key = api_key
        self._http = None

    def _client(self) -> httpx.AsyncClient:
        if self._http is None or self._http.is_closed:
            self._http = httpx.AsyncClient(
                base_url=self.api_url,
                headers={"Authorization": f"Bearer {self._api_key}"},
                timeout=30.0,
            )
        return self._http

    @staticmethod
    def _check(response: httpx.Response):
        if response.status_code >= 400:
            raise RuntimeError(
                f"Waggle API {response.request.method} {response.request.url.path} "
                f"failed with {response.status_code}: {response.text}"
            )

    async def _get(self, path, **params):
        r = await self._client().get(path, params=params or None)
        self._check(r)
        return r.json()

    async def _post(self, path, body: dict):
        r = await self._client().post(path, json=body)
        self._check(r)
        return r.json()

    async def _patch(self, path, body: dict):
        r = await self._client().patch(path, json=body)
        self._check(r)
        return r.json() if r.content else None

    async def _delete(self, path):
        r = await self._client().delete(path)
        self._check(r)

    async def aclose(self):
        if self._http is not None and not self._http.is_closed:
            await self._http.aclose()

    # --- Datacenters & slots -------------------------------------------------

    async def get_datacenter_by_name(self, name: str) -> dict:
        data = await self._get("/datacenters")
        for datacenter in data.get("items") or []:
            if datacenter["name"] == name:
                return datacenter
        raise LookupError(f"Datacenter {name!r} not found in Waggle")

    async def list_slots(self) -> list:
        """Return all slots (t-shirt VM sizes: name, vcpu, ram_gb, disk_gb) in the org."""
        data = await self._get("/slots")
        return data.get("items") or []

    async def get_slot_by_name(self, name: str) -> dict:
        data = await self._get("/slots", name=name)
        slots = data.get("items") or []
        if not slots:
            raise LookupError(f"Slot {name!r} not found in Waggle")
        return slots[0]

    # --- Pools & placements ------------------------------------------------------

    async def find_pools_by_name(self, name: str) -> list:
        data = await self._get("/pools")
        return [pool for pool in (data.get("items") or []) if pool["name"] == name]

    async def create_pool(self, datacenter_id: str, slot_id: str, name: str, desired_count: int) -> dict:
        """Create a pool; Waggle places its VMs across hypervisors (anti-affinity,
        all-or-nothing) and the placements become available via get_pool_placements."""
        logger.info(f"Creating Waggle pool {name!r} with desired_count={desired_count}")
        return await self._post("/pools", {
            "datacenter_id": datacenter_id,
            "slot_id": slot_id,
            "name": name,
            "desired_count": desired_count,
        })

    async def get_pool_placements(self, pool_id: str) -> list:
        data = await self._get(f"/pools/{pool_id}/placements")
        return data.get("items") or []

    async def set_placement_vmid(self, placement_id: str, vmid: int):
        """Backfill the externally-assigned Proxmox vmid onto a placement."""
        logger.info(f"Recording vmid {vmid} on Waggle placement {placement_id}")
        await self._patch(f"/placements/{placement_id}", {"vmid": vmid})

    async def delete_pool(self, pool_id: str):
        """Delete a pool and release all of its placements."""
        logger.info(f"Deleting Waggle pool {pool_id}")
        await self._delete(f"/pools/{pool_id}")
