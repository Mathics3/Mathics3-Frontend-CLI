#!/bin/bash
PACKAGE=mathicsscript

# FIXME put some of the below in a common routine
function finish {
  cd $mathicsscript_owd
}

cd $(dirname ${BASH_SOURCE[0]})
mathicsscript_owd=$(pwd)
trap finish EXIT

if ! source ./pyenv-versions ; then
    exit $?
fi


cd ..
source $PACKAGE/version.py
echo $__version__

pyversion=3.14
if ! pyenv local $pyversion ; then
    exit $?
fi
rm -fr build
python -m build --wheel
python -m build --sdist
finish
