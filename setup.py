# setup.py
from setuptools import setup, find_packages

setup(
    name='queuectl',
    version='1.0.0',
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        'click',
    ],
    entry_points={
        'console_scripts': [
            'queuectl = queuectl.cli:main',
        ],
    },
    author='Aravind Krishna S V',
    author_email='aravind120704@gmail.com',
    description='A CLI-based background job queue system.',
    long_description=open('README.md').read(),
    long_description_content_type='text/markdown',
    url='https://github.com/aravindkrishnasv/Job-Queueing',
)