# -*- coding: utf-8 -*-
# Copyright © 2020 Taylor C. Richberger (under an MIT license)
# Modifications (C) 2021 Stephen Gaito (under an Apache-2.0 license)

# The original code (examples/recursivewatch.py) has been taken from the
# https://gitlab.com/Taywee/asyncinotify project, on 2021/July/08,
# commit # 25b4aaf155d780027c8b9d7f17f5e8b25508c7ee

# The original code (examples/recursivewatch.py) has been adapted for use
# in the ComputePods AsyncWatchDo project using the original code's MIT
# license.

"""

This cpawd.fsWatcher module adapts the
[asyncinotify](https://asyncinotify.readthedocs.io/en/latest/)
[example](https://gitlab.com/Taywee/asyncinotify/-/blob/master/examples/recursivewatch.py)
to recursively watch directories or files either by a direct request, or
as they are created inside watched directories.

"""

import asyncio
from asyncinotify import Inotify, Event, Mask
import logging
from pathlib import Path
import sys
import traceback

class FSWatcher :
  """

  The `FSWatcher` class manages the Linux file system `inotify` watches
  for a given collection of directories or files. It provides a file
  change event stream via the iterable `recursive_watch` method.

  To allow for asynchronous operation, the "watches" are added to an
  `asyncio.Queue` managed by the `managePathsToWatchQueue` method. When
  used, this `managePathsToWatchQueue` method should be run inside its own
  `asyncio.Task`.

  """

  def __init__(self) :
    self.inotify            = Inotify()
    self.pathsToWatchQueue  = asyncio.Queue()
    self.logger             = logging.getLogger("FSWatcher")

    # We want Mask.MASK_ADD so that watches are updated
    # For the purposes of ComputePods we only care about:
    # Mask.CREATE, Mask.MODIFY, Mask.MOVE, and Mask.DELETE
    #
    # Other potentially (remotely) relevant mask values might be:
    # Mask.ACCESS would notify on any read/execs
    # Mask.ATTRIB would notify on changes to timestamps, permissions, user/group ID
    # Mask.CLOSE would notify on files being closed (after being opened?)
    # Mask.OPEN would notify on files being opened
    # Mask.UNMOUNT would notify on a file system being unmounted
    #
    self.cpMask = Mask.CLOSE_WRITE | Mask.CREATE | Mask.MODIFY | Mask.MOVE | Mask.DELETE
    #
    # Now we add in Masks we need for this module's book-keeping
    #
    self.wrMask = self.cpMask | Mask.MASK_ADD | Mask.MOVED_FROM | Mask.MOVED_TO | Mask.CREATE | Mask.DELETE_SELF | Mask.IGNORED

########################################################################

  # Add/manage paths to watch

  def get_directories_recursive(self, path) :
    '''

    Recursively list all directories under path, including path itself, if
    it's a directory.

    The path itself is always yielded before its children are iterated, so you
    can pre-process a path (by watching it with inotify) before you get the
    directory listing.

    '''
    if path.is_dir() :
      yield path
      for child in path.iterdir():
        yield from self.get_directories_recursive(child)
    elif path.is_file() :
      yield path

  async def watchAPath(self, pathToWatch) :
    """

    Add a single directory or file to be watched by this instance of
    `FSWatcher` to the `pathsToWatchQueue`.

    """
    self.logger.debug("Adding path to watch queue {}".format(pathToWatch))
    await self.pathsToWatchQueue.put(pathToWatch)

  async def managePathsToWatchQueue(self) :
    """

    Implement all (pending) requests to watch a directory or file which
    are in the `pathsToWatchQueue`.

    The paths contained in all directories are themselves recursively
    added to the `pathsToWatchQueue`.

    """

    while True :
      aPathToWatch = await self.pathsToWatchQueue.get()
      for aPath in self.get_directories_recursive(Path(aPathToWatch)) :
        try :
          self.inotify.add_watch(aPath, self.wrMask)
          self.logger.info(f'INIT: watching {aPath}')
        except PermissionError as err :
          pass
        except Exception as err:
          print(f"Exception whild trying to watch: [{aPath}]")
          traceback.print_exc(err)
          # we can't watch this path just yet...
          # ... schedule its parent and try again...
          await self.watchAPath(aPath.parent)
      self.pathsToWatchQueue.task_done()

########################################################################

  # provide the inotify events stream

  async def watchForFileSystemEvents(self):
    """

    An asynchronously interable method which yields file system change
    events.

    """

    # Things that can throw this off:
    #
    # * Moving a watched directory out of the watch tree (will still
    #   generate events even when outside of directory tree)
    #
    # * Doing two changes on a directory or something before the program
    #   has a time to handle it (this will also throw off a lot of inotify
    #   code, though)
    #
    # * Moving a watched directory within a watched directory will get the
    #   wrong path.  This needs to use the cookie system to link events
    #   together and complete the move properly, which can still make some
    #   events get the wrong path if you get file events during the move or
    #   something silly like that, since MOVED_FROM and MOVED_TO aren't
    #   guaranteed to be contiguous.  That exercise is left up to the
    #   reader.
    #
    # * Trying to watch a path that doesn't exist won't automatically
    #   create it or anything of the sort.
    #
    # * Deleting and recreating or moving the watched directory won't do
    #   anything special, but it probably should.
    #
    async for event in self.inotify:

      # If this is a creation event, add a watch for the new path (and its
      # subdirectories if any)
      #
      if Mask.CREATE in event.mask and event.path is not None :
        await self.watchAPath(event.path)

      # If there are some bits in the cpMask in the event.mask yield this
      # event
      #
      if event.mask & self.cpMask:
        yield event
      else:
        # Note that these events are needed for cleanup purposes.
        # We'll always get IGNORED events so the watch can be removed
        # from the inotify.  We don't need to do anything with the
        # events, but they do need to be generated for cleanup.
        # We don't need to pass IGNORED events up, because the end-user
        # doesn't have the inotify instance anyway, and IGNORED is just
        # used for management purposes.
        #
        self.logger.debug(f'UNYIELDED EVENT: {event}')

########################################################################
