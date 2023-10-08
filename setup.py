
from setuptools import setup, find_packages

setup(
    name='glueops-helpers',
    version='0.0.4',
    packages=find_packages(),
    install_requires=[
        'requests==2.31.0',
        'boto3==1.28.62',
        'slowapi==0.1.8',
        'cryptography==41.0.4',
        'jwt==1.3.1',
        'kubernetes==28.1.0',
        'requests==2.31.0',
        'fastapi==0.103.2',
        'qrcode==7.4.2',
        'Pillow==10.0.1',
        'uvicorn[standard]==0.23.2',
        'gunicorn==21.2.0',
        'PyYAML==6.0.1',
        'python-dotenv==1.0.0',
        'smart-open=6.4.0'
    ],
    entry_points={
        # If needed, you can add entry points for command line utilities here
    }
)
