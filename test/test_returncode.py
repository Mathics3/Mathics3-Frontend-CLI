import pytest
import sys
import subprocess

import os.path as osp

# FIXME: We need to come up with some other sort of test.
pytest.mark.skipif(
    sys.platform == "win32",
    reason="This module is not supported or required on MS Windows",
)


def get_testdir():
    filename = osp.normcase(osp.dirname(osp.abspath(__file__)))
    return osp.realpath(filename)


def test_returncode():
    assert subprocess.run(["mathicsscript", "-c", "Quit[5]"]).returncode == 5
    assert subprocess.run(["mathicsscript", "-c", "1 + 2'"]).returncode == 0
    assert subprocess.run(["mathicsscript", "-c", "Quit[0]"]).returncode == 0

    gcd_file = osp.join(get_testdir(), "data", "recursive-gcd.m")
    # We add --readline None for OSX and Windows which don't interact well
    # with tty's in a CI environment. TODO: separate out Ubuntu and
    # use prompt_readline for that?
    assert (
        subprocess.run(
            ["mathicsscript", "--readline", "None", "-f", gcd_file]
        ).returncode
        == 0
    )


if __name__ == "__main__":
    test_returncode()
