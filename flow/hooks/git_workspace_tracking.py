# Copyright (c) 2018 The Regents of the University of Michigan
# All rights reserved.
# This software is licensed under the BSD 3-Clause License.
import os
import json
import logging
from collections import defaultdict

import git

from .git_util import collect_metadata_with_git as collect_metadata


logger = logging.getLogger('git_tracking')

GIT_COMMIT_MSG = """{title}

*This commit was auto-generated.*
"""


_WARNINGS = defaultdict(set)


def _git_ignore(root, entries):
    "Do not commit hidden files to the git repository."
    fn_ignore = os.path.join(root, '.gitignore')
    with open(fn_ignore, mode='a+') as file:
        lines = file.readlines()
        for entry in entries:
            if entry not in lines:
                logger.info("Adding  '{}' to '{}'.".format(entry, fn_ignore))
                file.write(entry + '\n')


def _git_ignored(root):
    fn_ignore = os.path.join(root, '.gitignore')
    with open(fn_ignore, mode='r') as file:
        return file.readlines()


def _commit(repo, title):
    try:
        repo.git.commit('-m', GIT_COMMIT_MSG.format(title=title))
    except git.exc.GitCommandError as error:
        if "nothing to commit, working tree clean" in str(error):
            pass
        else:
            raise


class TrackWorkspaceWithGit(object):

    def __init__(self, per_job=True, ignore=None):
        self._per_job = per_job
        self._ignore = ignore
        self._warnings = defaultdict(set)

    def _get_repo(self, operation):
        if self._per_job:
            root = operation.job.workspace()
        else:
            root = operation.job._project.workspace()

        try:
            return git.Repo(root)
        except git.exc.InvalidGitRepositoryError:
            logger.info("Initializing git repo for '{}'".format(root))
            if self._ignore:
                _git_ignore(root, self._ignore)
            return git.Repo.init(root)

    def commit_before(self, operation):
        metadata = collect_metadata(operation)
        metadata['stage'] = 'prior'
        repo = self._get_repo(operation)
        repo.git.add(A=True)
        _commit(repo, "Before executing operation {}.".format(operation))

    def commit_after(self, operation, error=None):
        metadata = collect_metadata(operation)
        metadata['stage'] = 'post'
        metadata['error'] = None if error is None else str(error)
        repo = self._get_repo(operation)
        repo.git.add(A=True)
        if error:
            _commit(repo, "Executed operation {}.\n\nThe execution failed "
                          "with error '{}'.".format(operation, error))
        else:
            _commit(repo, "Executed operation {}.".format(operation))
        repo.git.notes('append', repo.commit(), '-m', 'signac:' + json.dumps(metadata))

    def install_hooks(self, project):
        project.hooks.on_start.append(self.commit_before)
        project.hooks.on_success.append(self.commit_after)
        project.hooks.on_fail.append(self.commit_after)
        return project

    __call__ = install_hooks
