
from setuptools import setup, find_packages

setup(
    name='glueops-helpers',
    version='0.0.11',
    packages=find_packages(),
    install_requires=[
        'requests',
        'boto3',
        'slowapi',
        'cryptography'
    ],
    entry_points={
        # If needed, you can add entry points for command line utilities here
    }
)
