
from distutils.core import setup

setup(name='SQLAlchemy-serializer',
      version='0.2',
      description='Mixin for SQLAlchemy-models serialization without pain',
      author='Y-Bro',
      url='https://github.com/n0nSmoker/SQLAlchemy-serializer.git',
      keywords=['sqlalchemy', 'serialize', 'to_dict'],
      packages=['sqlalchemy_serializer'],
      install_requires=[
        'SQLAlchemy',
        'Flask-Babel',
        'Flask-Builder',
        'blinker',
      ]
)


