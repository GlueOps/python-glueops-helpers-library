from typing import List

import boto3
from botocore.client import BaseClient


def create_aws_client(service: str, region: str = 'us-east-1') -> BaseClient:
    return boto3.client(service, region_name=region)


def get_resource_arns_using_tags(
    tags: List[dict],
    aws_resource_filters: List[str]
) -> List[str]:
    """Retrieve ARNs of resources with specific tags.

    Args:
        tags (List[dict]): _in format {"Key": "<the-key>", "Value": "<the-value>"}
        aws_resource_filters (List[str]): AWS resource filter list

    Returns:
        List[str]: ARNs of resources
    """
    tagging = create_aws_client('resourcegroupstaggingapi')
    tags = {item['Key']: item['Value'] for item in tags}
    response = tagging.get_resources(
        TagFilters=[
            {'Key': key, 'Values': [value]} for key, value in tags.items()
        ],
        ResourceTypeFilters=aws_resource_filters
    )
    return [
        item['ResourceARN']
        for item in response.get('ResourceTagMappingList', [])
    ]
