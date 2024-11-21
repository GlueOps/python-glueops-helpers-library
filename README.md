# GlueOps Helpers Library

The GlueOps Helpers Library is a collection of utility functions and classes designed to simplify common tasks in Python projects. This library includes helpers for logging, AWS interactions, Kubernetes configuration, and more.

## Installation

To install the GlueOps Helpers Library, you can use pip with the following command:

```bash
pip install https://github.com/GlueOps/python-glueops-helpers-library/archive/refs/tags/v0.6.0.zip
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