# A GNU Makefile to run various tasks - compatibility for us old-timers.

# Note: This makefile include remake-style target comments.
# These comments before the targets start with #:
# remake --tasks to shows the targets and the comments

GIT2CL ?= admin-tools/git2cl
PYTHON ?= python3
PIP ?= pip3
RM  ?= rm

.PHONY: all build \
       ChangeLog-without-corrections \
       check clean inputrc develop dist doc \
       pytest sdist test \
       rmChangeLog runner

#: Default target - same as "develop"
all: develop

#: build everything needed to install
build: inputrc
	$(PYTHON) ./setup.py build

#: Set up to run from the source tree
develop: inputrc
	$(PIP) install -e .

#: Make distirbution: wheel and tarball
dist:
	./admin-tools/make-dist.sh

#: Run mathicsscript and reload on file changes to the source
runner:
	watchgod mathicsscript.__main__.main

#: Install mathicsscript
install: inputrc
	$(PYTHON) setup.py install

#: Run tests. You can set environment variable "o" for pytest options
check: inputrc
	$(PYTHON) -m pytest test $o

inputrc: mathicsscript/data/inputrc-unicode mathicsscript/data/inputrc-no-unicode

mathicsscript/data/inputrc-unicode mathicsscript/data/inputrc-no-unicode mathicsscript/data/inputrc-unicode/mma-tables.json:
	$(SHELL) ./admin-tools/make-JSON-tables.sh

# Check StructuredText long description formatting
check-rst:
	$(PYTHON) setup.py --long-description | ./rst2html.py > mathicsscript.html

#: Remove derived files
clean:
	@find . -name "*.pyc" -type f -delete
	@rm mathicsscript/inputrc-no-unicode mathicsscript/inputrc-unicode || true

#: Create source tarball
sdist: check-rst
	$(PYTHON) ./setup.py sdist

#: Remove ChangeLog
rmChangeLog:
	$(RM) ChangeLog || true

#: Create ChangeLog from version control without corrections
ChangeLog-without-corrections:
	git log --pretty --numstat --summary | $(GIT2CL) >ChangeLog

#: Create a ChangeLog from git via git log and git2cl
ChangeLog: rmChangeLog ChangeLog-without-corrections
	patch ChangeLog < ChangeLog-spell-corrected.diff
