"""
Cloud Storage Integration Modules
Provides integrations with cloud storage services like AWS S3
"""

from ...registry import register_module
import os
import base64


@register_module(
    module_id='cloud.aws_s3.upload',
    version='1.0.0',
    category='cloud',
    tags=['cloud', 'aws', 's3', 'storage', 'upload', 'file'],
    label='AWS S3 Upload',
    label_key='modules.cloud.aws_s3.upload.label',
    description='Upload a file or data to AWS S3 bucket',
    description_key='modules.cloud.aws_s3.upload.description',
    icon='Cloud',
    color='#FF9900',

    # Connection types
    input_types=['any'],
    output_types=['any'],

    # Phase 2: Execution settings
    timeout=60,  # Cloud uploads can take time depending on file size
    retryable=True,  # Network errors can be retried
    max_retries=3,
    concurrent_safe=True,  # Multiple uploads can run in parallel

    # Phase 2: Security settings
    requires_credentials=True,  # Needs AWS credentials
    handles_sensitive_data=True,  # Files may contain sensitive data
    required_permissions=['network.access', 'cloud.storage'],

    params_schema={
        'aws_access_key_id': {
            'type': 'string',
            'label': 'AWS Access Key ID',
            'label_key': 'modules.cloud.aws_s3.upload.params.aws_access_key_id.label',
            'description': 'AWS access key ID (defaults to env.AWS_ACCESS_KEY_ID)',
            'description_key': 'modules.cloud.aws_s3.upload.params.aws_access_key_id.description',
            'placeholder': '${env.AWS_ACCESS_KEY_ID}',
            'required': False,
            'secret': True
        },
        'aws_secret_access_key': {
            'type': 'string',
            'label': 'AWS Secret Access Key',
            'label_key': 'modules.cloud.aws_s3.upload.params.aws_secret_access_key.label',
            'description': 'AWS secret access key (defaults to env.AWS_SECRET_ACCESS_KEY)',
            'description_key': 'modules.cloud.aws_s3.upload.params.aws_secret_access_key.description',
            'placeholder': '${env.AWS_SECRET_ACCESS_KEY}',
            'required': False,
            'secret': True
        },
        'region': {
            'type': 'string',
            'label': 'Region',
            'label_key': 'modules.cloud.aws_s3.upload.params.region.label',
            'description': 'AWS region (defaults to env.AWS_REGION or us-east-1)',
            'description_key': 'modules.cloud.aws_s3.upload.params.region.description',
            'placeholder': '${env.AWS_REGION}',
            'default': 'us-east-1',
            'required': False
        },
        'bucket': {
            'type': 'string',
            'label': 'Bucket Name',
            'label_key': 'modules.cloud.aws_s3.upload.params.bucket.label',
            'description': 'S3 bucket name',
            'description_key': 'modules.cloud.aws_s3.upload.params.bucket.description',
            'required': True,
            'placeholder': 'my-bucket'
        },
        'key': {
            'type': 'string',
            'label': 'Object Key',
            'label_key': 'modules.cloud.aws_s3.upload.params.key.label',
            'description': 'S3 object key (file path in bucket)',
            'description_key': 'modules.cloud.aws_s3.upload.params.key.description',
            'required': True,
            'placeholder': 'uploads/file.txt'
        },
        'file_path': {
            'type': 'string',
            'label': 'File Path',
            'label_key': 'modules.cloud.aws_s3.upload.params.file_path.label',
            'description': 'Local file path to upload',
            'description_key': 'modules.cloud.aws_s3.upload.params.file_path.description',
            'required': False,
            'help': 'Either file_path or content must be provided'
        },
        'content': {
            'type': 'string',
            'label': 'Content',
            'label_key': 'modules.cloud.aws_s3.upload.params.content.label',
            'description': 'File content to upload (as string or base64)',
            'description_key': 'modules.cloud.aws_s3.upload.params.content.description',
            'required': False,
            'multiline': True,
            'help': 'Either file_path or content must be provided'
        },
        'content_type': {
            'type': 'string',
            'label': 'Content Type',
            'label_key': 'modules.cloud.aws_s3.upload.params.content_type.label',
            'description': 'MIME type of the file',
            'description_key': 'modules.cloud.aws_s3.upload.params.content_type.description',
            'required': False,
            'placeholder': 'text/plain',
            'help': 'Auto-detected if not provided'
        },
        'acl': {
            'type': 'string',
            'label': 'ACL',
            'label_key': 'modules.cloud.aws_s3.upload.params.acl.label',
            'description': 'Access control list for the object',
            'description_key': 'modules.cloud.aws_s3.upload.params.acl.description',
            'required': False,
            'default': 'private',
            'options': [
                {'value': 'private', 'label': 'Private'},
                {'value': 'public-read', 'label': 'Public Read'},
                {'value': 'public-read-write', 'label': 'Public Read/Write'}
            ]
        }
    },
    output_schema={
        'url': {
            'type': 'string',
            'description': 'S3 URL of uploaded object'
        },
        'bucket': {
            'type': 'string',
            'description': 'Bucket name'
        },
        'key': {
            'type': 'string',
            'description': 'Object key'
        },
        'etag': {
            'type': 'string',
            'description': 'ETag of uploaded object'
        }
    },
    examples=[
        {
            'title': 'Upload text content',
            'title_key': 'modules.cloud.aws_s3.upload.examples.text.title',
            'params': {
                'bucket': 'my-bucket',
                'key': 'reports/daily-${timestamp}.txt',
                'content': '${report_text}',
                'content_type': 'text/plain'
            }
        },
        {
            'title': 'Upload local file',
            'title_key': 'modules.cloud.aws_s3.upload.examples.file.title',
            'params': {
                'bucket': 'my-bucket',
                'key': 'backups/database.sql',
                'file_path': '/tmp/backup.sql',
                'acl': 'private'
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT',
    docs_url='https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/s3.html'
)
async def aws_s3_upload(context):
    """Upload file to AWS S3"""
    params = context['params']

    try:
        import aioboto3
    except ImportError:
        raise ImportError("aioboto3 package required. Install with: pip install aioboto3")

    # Get AWS credentials
    aws_access_key_id = params.get('aws_access_key_id') or os.getenv('AWS_ACCESS_KEY_ID')
    aws_secret_access_key = params.get('aws_secret_access_key') or os.getenv('AWS_SECRET_ACCESS_KEY')
    region = params.get('region') or os.getenv('AWS_REGION', 'us-east-1')

    if not aws_access_key_id or not aws_secret_access_key:
        raise ValueError("AWS credentials required: set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY")

    bucket = params['bucket']
    key = params['key']
    file_path = params.get('file_path')
    content = params.get('content')

    if not file_path and not content:
        raise ValueError("Either 'file_path' or 'content' must be provided")

    # Prepare upload
    session = aioboto3.Session(
        aws_access_key_id=aws_access_key_id,
        aws_secret_access_key=aws_secret_access_key,
        region_name=region
    )

    extra_args = {}
    if params.get('content_type'):
        extra_args['ContentType'] = params['content_type']
    if params.get('acl'):
        extra_args['ACL'] = params['acl']

    async with session.client('s3') as s3:
        if file_path:
            # Upload from file
            await s3.upload_file(file_path, bucket, key, ExtraArgs=extra_args)
        else:
            # Upload from content
            body = content.encode('utf-8') if isinstance(content, str) else content
            await s3.put_object(Bucket=bucket, Key=key, Body=body, **extra_args)

        # Get object info
        response = await s3.head_object(Bucket=bucket, Key=key)
        etag = response.get('ETag', '').strip('"')

    url = f"https://{bucket}.s3.{region}.amazonaws.com/{key}"

    return {
        'url': url,
        'bucket': bucket,
        'key': key,
        'etag': etag
    }


@register_module(
    module_id='cloud.aws_s3.download',
    version='1.0.0',
    category='cloud',
    tags=['cloud', 'aws', 's3', 'storage', 'download', 'file'],
    label='AWS S3 Download',
    label_key='modules.cloud.aws_s3.download.label',
    description='Download a file from AWS S3 bucket',
    description_key='modules.cloud.aws_s3.download.description',
    icon='Cloud',
    color='#FF9900',

    # Connection types
    input_types=['any'],
    output_types=['any'],

    # Phase 2: Execution settings
    timeout=60,  # Cloud downloads can take time depending on file size
    retryable=True,  # Network errors can be retried
    max_retries=3,
    concurrent_safe=True,  # Multiple downloads can run in parallel

    # Phase 2: Security settings
    requires_credentials=True,  # Needs AWS credentials
    handles_sensitive_data=True,  # Files may contain sensitive data
    required_permissions=['network.access', 'cloud.storage'],

    params_schema={
        'aws_access_key_id': {
            'type': 'string',
            'label': 'AWS Access Key ID',
            'label_key': 'modules.cloud.aws_s3.download.params.aws_access_key_id.label',
            'description': 'AWS access key ID (defaults to env.AWS_ACCESS_KEY_ID)',
            'description_key': 'modules.cloud.aws_s3.download.params.aws_access_key_id.description',
            'placeholder': '${env.AWS_ACCESS_KEY_ID}',
            'required': False,
            'secret': True
        },
        'aws_secret_access_key': {
            'type': 'string',
            'label': 'AWS Secret Access Key',
            'label_key': 'modules.cloud.aws_s3.download.params.aws_secret_access_key.label',
            'description': 'AWS secret access key (defaults to env.AWS_SECRET_ACCESS_KEY)',
            'description_key': 'modules.cloud.aws_s3.download.params.aws_secret_access_key.description',
            'placeholder': '${env.AWS_SECRET_ACCESS_KEY}',
            'required': False,
            'secret': True
        },
        'region': {
            'type': 'string',
            'label': 'Region',
            'label_key': 'modules.cloud.aws_s3.download.params.region.label',
            'description': 'AWS region (defaults to env.AWS_REGION or us-east-1)',
            'description_key': 'modules.cloud.aws_s3.download.params.region.description',
            'placeholder': '${env.AWS_REGION}',
            'default': 'us-east-1',
            'required': False
        },
        'bucket': {
            'type': 'string',
            'label': 'Bucket Name',
            'label_key': 'modules.cloud.aws_s3.download.params.bucket.label',
            'description': 'S3 bucket name',
            'description_key': 'modules.cloud.aws_s3.download.params.bucket.description',
            'required': True
        },
        'key': {
            'type': 'string',
            'label': 'Object Key',
            'label_key': 'modules.cloud.aws_s3.download.params.key.label',
            'description': 'S3 object key (file path in bucket)',
            'description_key': 'modules.cloud.aws_s3.download.params.key.description',
            'required': True
        },
        'file_path': {
            'type': 'string',
            'label': 'Save to File Path',
            'label_key': 'modules.cloud.aws_s3.download.params.file_path.label',
            'description': 'Local file path to save downloaded content',
            'description_key': 'modules.cloud.aws_s3.download.params.file_path.description',
            'required': False,
            'help': 'If not provided, content is returned in memory'
        }
    },
    output_schema={
        'content': {
            'type': 'string',
            'description': 'File content (if file_path not provided)'
        },
        'file_path': {
            'type': 'string',
            'description': 'Path where file was saved (if file_path provided)'
        },
        'size': {
            'type': 'number',
            'description': 'File size in bytes'
        },
        'content_type': {
            'type': 'string',
            'description': 'MIME type of the file'
        }
    },
    examples=[
        {
            'title': 'Download to memory',
            'title_key': 'modules.cloud.aws_s3.download.examples.memory.title',
            'params': {
                'bucket': 'my-bucket',
                'key': 'data/config.json'
            }
        },
        {
            'title': 'Download to file',
            'title_key': 'modules.cloud.aws_s3.download.examples.file.title',
            'params': {
                'bucket': 'my-bucket',
                'key': 'backups/database.sql',
                'file_path': '/tmp/downloaded.sql'
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT',
    docs_url='https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/s3.html'
)
async def aws_s3_download(context):
    """Download file from AWS S3"""
    params = context['params']

    try:
        import aioboto3
    except ImportError:
        raise ImportError("aioboto3 package required. Install with: pip install aioboto3")

    # Get AWS credentials
    aws_access_key_id = params.get('aws_access_key_id') or os.getenv('AWS_ACCESS_KEY_ID')
    aws_secret_access_key = params.get('aws_secret_access_key') or os.getenv('AWS_SECRET_ACCESS_KEY')
    region = params.get('region') or os.getenv('AWS_REGION', 'us-east-1')

    if not aws_access_key_id or not aws_secret_access_key:
        raise ValueError("AWS credentials required: set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY")

    bucket = params['bucket']
    key = params['key']
    file_path = params.get('file_path')

    session = aioboto3.Session(
        aws_access_key_id=aws_access_key_id,
        aws_secret_access_key=aws_secret_access_key,
        region_name=region
    )

    async with session.client('s3') as s3:
        if file_path:
            # Download to file
            await s3.download_file(bucket, key, file_path)

            # Get metadata
            response = await s3.head_object(Bucket=bucket, Key=key)

            return {
                'file_path': file_path,
                'size': response.get('ContentLength', 0),
                'content_type': response.get('ContentType', '')
            }
        else:
            # Download to memory
            response = await s3.get_object(Bucket=bucket, Key=key)

            async with response['Body'] as stream:
                content = await stream.read()

            return {
                'content': content.decode('utf-8'),
                'size': response.get('ContentLength', 0),
                'content_type': response.get('ContentType', '')
            }
