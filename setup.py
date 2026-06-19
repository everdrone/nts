import re
import setuptools


def get_version():
    # single source of truth: nts/downloader.py's __version__ (also what
    # `nts --version` prints). read it without importing, so the build doesn't
    # require the runtime dependencies to be installed.
    with open("nts/downloader.py", encoding="utf-8") as f:
        match = re.search(r'^__version__\s*=\s*[\'"]([^\'"]+)[\'"]', f.read(), re.M)
    if not match:
        raise RuntimeError("could not find __version__ in nts/downloader.py")
    return match.group(1)


setuptools.setup(
    name="nts-everdrone",
    version=get_version(),
    author="Giorgio Tropiano",
    author_email="giorgiotropiano@gmail.com",
    description="NTS Radio downloader tool",
    long_description=open('readme.md').read(),
    long_description_content_type="text/markdown",
    url="https://github.com/everdrone/nts",
    packages=setuptools.find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    license='MIT',
    entry_points={'console_scripts': ['nts=nts.cli:main']},
    install_requires=[
        'yt-dlp==2024.7.25',
        'beautifulsoup4==4.9.3',
        'mutagen==1.45.1',
        'requests==2.32.4',
        'cssutils==2.7.1',
        'ffmpeg-python==0.2.0',
        'music-tag==0.4.3',
        'pillow==10.4.0',
    ],
    python_requires='>=3.7.5',
)
