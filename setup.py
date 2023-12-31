
from setuptools import setup, find_packages

setup(
    name='glueops-helpers',
    version='0.4.1',
    packages=find_packages(),
    install_requires=[
        'requests',
        'boto3',
        'cryptography',
        'kubernetes'
    ],
    entry_points={
        # If needed, you can add entry points for command line utilities here
    }
)
