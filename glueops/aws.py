import boto3


def create_aws_client(service):
    return boto3.client(service, region_name='us-east-1')


def get_resource_arns_using_tags(tags, aws_resource_filters):
    """Retrieve ARNs of resources with specific tags."""
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
