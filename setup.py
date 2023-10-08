
from setuptools import setup, find_packages

setup(
    name='glueops-helpers',
    version='0.0.1',
    packages=find_packages(),
    install_requires=[
        'requests==2.31.0',
        'boto3==1.28.62',
        'slowapi=0.1.8',
        'cryptography==41.0.4'
    ],
    entry_points={
        # If needed, you can add entry points for command line utilities here
    }
)
