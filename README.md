# GlueOps Helpers Library

The GlueOps Helpers Library is a collection of utility functions and classes designed to simplify common tasks in Python projects. This library includes helpers for logging, AWS interactions, Kubernetes configuration, and more.

## Installation

To install the GlueOps Helpers Library, you can use pip with the following command:

```bash
pip install https://github.com/GlueOps/python-glueops-helpers-library/archive/refs/tags/v0.7.5.zip
```

# Usage

## Logging

The library provides a logging configuration utility that sets up a JSON formatter for structured logging.

```python
import os
from glueops import setup_logging

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
logger = setup_logging.configure(level=LOG_LEVEL)

logger.info("This is an info message")
logger.error("This is an error message")
```

## AWS
The library includes helpers for creating AWS clients and retrieving resources based on tags.

```python
from glueops.aws import create_aws_client, get_resource_arns_using_tags

# Create an AWS client
s3_client = create_aws_client('s3')

# Get resource ARNs using tags
tags = [{'Key': 'Environment', 'Value': 'Production'}]
resource_arns = get_resource_arns_using_tags(tags, ['s3'])
print(resource_arns)
```

## Kubernetes

```python
import os
from glueops.setup_kubernetes import load_kubernetes_config

logger = setup_logging.configure(level="INFO")
v1, custom_api = load_kubernetes_config(logger)

# Example: List all pods in the default namespace
pods = v1.list_namespaced_pod(namespace='default')
for pod in pods.items:
    print(pod.metadata.name)
```

## Vault

The library includes a client for interacting with HashiCorp Vault, supporting both Kubernetes and Pomerium authentication.

```python
from glueops.vault_client import VaultClient

vault_url = "https://vault.example.com"
kubernetes_role = "my-role"
vault_client = VaultClient(vault_url, kubernetes_role)

# Get data from Vault
secret_path = "secret/data/my-secret"
data = vault_client.get_data_from_vault(secret_path)
print(data)

# Write data to Vault
data_to_write = {"key": "value"}
vault_client.write_data_to_vault(secret_path, data_to_write)
```

## GetOutline

The library provides a client for interacting with the GetOutline API for managing documents.

```python
from glueops.getoutline import GetOutlineClient

api_url = "https://api.getoutline.com"
document_id = "your_document_id"
api_token = "your_api_token"
outline_client = GetOutlineClient(api_url, document_id, api_token)

# Create a new document
parent_document_id = "parent_document_id"
title = "New Document"
text = "This is the content of the new document."
outline_client.create_document(parent_document_id, title, text)
```
## Proxmox

Async client for the Proxmox VE REST API covering the VM-provisioning surface shared by GlueOps services: task polling (bounded, with stalled-task stop), image caching via download-url (requires PVE 8.4+ for qcow2 `import` content), cloud-init NoCloud ISO build/upload, VM lifecycle (create/resize/start/idempotent delete), native-tag discovery, and guest-agent queries (exec, cloud-init wait, validated IPv4 discovery).

```python
from glueops.proxmox import ProxmoxClient, build_cloudinit_iso

client = ProxmoxClient(
    host="pve.example.com",
    token_id="automation@pve!mytoken",
    token_secret="your_token_secret",
    storage="local-zfs",
    download_server_url="https://images.example.com",  # hosts <image>.qcow2
)

cached = await client.ensure_image_cached("node1", "debian-13-generic-amd64")  # optional: checksum=..., cache_name=...
iso = build_cloudinit_iso(user_data=b"#cloud-config\n...", meta_data=b"instance-id: my-tenant-vm1\n")
await client.upload_iso("node1", "my-tenant-vm1-cloudinit.iso", iso)
vmid = await client.get_next_vmid()
await client.create_vm(node="node1", vmid=vmid, vm_name="my-tenant-vm1", vcpus=2, memory_mb=4096,
                       image="debian-13-generic-amd64", iso_filename="my-tenant-vm1-cloudinit.iso",
                       tags=["my-app", "my-tenant"], bridge="vmbr_public")
await client.start_vm("node1", vmid)
await client.wait_for_cloud_init("node1", vmid)
ip = await client.get_vm_ipv4("node1", vmid)

# The cloud-init ISO often embeds credentials — remove it once the VM is up
await client.eject_and_delete_iso("node1", vmid, "my-tenant-vm1-cloudinit.iso")

# Later: find and delete everything for a tenant by tags. VM purge never removes
# standalone ISO volumes, so also sweep any orphaned cloud-init ISOs (the sweep
# skips any ISO still referenced by a VM config). Keep the
# tenant prefix in ISO names AND in the sweep regex — an unscoped pattern would
# delete other tenants' in-flight cloud-init ISOs on a shared cluster.
for vm in await client.list_vms_by_tags(["my-app", "my-tenant"]):
    await client.delete_vm(vm["node"], vm["vmid"])
await client.delete_isos_matching(r"my-tenant-vm\d+-cloudinit\.iso")
```

## Waggle

Async client for the [Waggle](https://github.com/glueops/waggle) placement oracle. Waggle decides where VMs go but does not create them: create a pool against a pre-existing datacenter and slot, read the placements (one hypervisor per VM), provision the VMs yourself (e.g. with `ProxmoxClient`), then backfill each Proxmox vmid.

```python
from glueops.waggle import WaggleClient

waggle = WaggleClient("https://waggle.example.com", "wgl_your_api_key")

datacenter = await waggle.get_datacenter_by_name("dc1")
slot = await waggle.get_slot_by_name("2vcpu-4gb-40gb")
pool = await waggle.create_pool(datacenter["id"], slot["id"], "my-pool", desired_count=3)
placements = await waggle.get_pool_placements(pool["id"])
for placement in placements:
    # ... create the VM on placement["hypervisor_name"] via ProxmoxClient ...
    await waggle.set_placement_vmid(placement["id"], int(vmid))

# Teardown
for pool in await waggle.find_pools_by_name("my-pool"):
    await waggle.delete_pool(pool["id"])
```
