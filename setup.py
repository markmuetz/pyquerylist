#!/usr/bin/env python
from pathlib import Path
import subprocess as sp

try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup

version = sp.run(
    'python pyquerylist/version.py',
    check=True,
    shell=True,
    stdout=sp.PIPE,
    stderr=sp.PIPE,
    encoding='utf8',
).stdout


def read(fname):
    try:
        return (Path(__file__).parent / fname).read_text()
    except (IOError, OSError, FileNotFoundError):
        return ''


setup(
    name='pyquerylist',
    version=version,
    description='List that you can query',
    include_package_data=True,
    license='LICENSE',
    long_description=read('README.md'),
    long_description_content_type='text/markdown',
    author='Mark Muetzelfeldt',
    author_email='mark.muetzelfeldt@reading.ac.uk',
    maintainer='Mark Muetzelfeldt',
    maintainer_email='mark.muetzelfeldt@reading.ac.uk',
    url='https://github.com/markmuetz/pyquerylist',
    project_urls={
        'Bug Tracker': 'https://github.com/markmuetz/pyquerylist/issues',
    },
    packages=[
        'pyquerylist',
    ],
    install_requires=[
        'tabulate',
    ],
    python_requires='>=3.6',
    classifiers=[
        'Environment :: Console',
        'Natural Language :: English',
        'Operating System :: POSIX :: Linux',
        'Programming Language :: Python :: 3.9',
        'Development Status :: 4 - Beta',
    ],
)
