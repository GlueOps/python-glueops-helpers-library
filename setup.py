
from setuptools import setup, find_packages

setup(
    name='glueops-helpers',
    version='0.8.0',
    packages=find_packages(),
    install_requires=[
        'requests',
        'boto3',
        'cryptography',
        'kubernetes',
        'httpx',
        'pycdlib'
    ],
    entry_points={
        # If needed, you can add entry points for command line utilities here
    }
)
