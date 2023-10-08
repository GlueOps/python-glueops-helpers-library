import boto3
import glueops.logging

logger = glueops.logging.configure()


def create_aws_client(service):
    return boto3.client(service, region_name='us-east-1')


def get_resource_arns_using_tags(tags, aws_resource_filters):
    """Retrieve ARNs of resources with specific tags."""
    logger.info(
        f"Checking to see if this arn was already requested/created with tags: {tags}")
    tagging = create_aws_client('resourcegroupstaggingapi')
    tags = {item['Key']: item['Value'] for item in tags}
    response = tagging.get_resources(
        TagFilters=[
            {'Key': key, 'Values': [value]} for key, value in tags.items()
        ],
        ResourceTypeFilters=aws_resource_filters
    )

    arns = [item['ResourceARN']
            for item in response.get('ResourceTagMappingList', [])]

    return arns
