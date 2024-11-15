from setuptools import setup, find_packages


setup(
    name='minbt', 
    version='0.0.2', 
    packages=find_packages(),
    description='Minimalistic Backtesting Library',
    install_requires = ['numpy', 'pandas', 'polars', 'loguru'],
    scripts=[],
    python_requires = '>=3',
    include_package_data=True,
    author='Liu Shengli',
    url='http://github.com/gseismic/minbt',
    zip_safe=False,
    author_email='liushengli203@163.com'
)
