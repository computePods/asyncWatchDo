""" This cpawd.taskRunner module implements the running of all watch-do
tasks.

----

The following description is illustrated in the interaction diagram below.

The top level `runTasks` method initiates an `asyncio.Tasks` running the
`watchDo` method for each watch-do task. The `watchDo` method `reStart`s
an `asyncio.Task`, `taskRunner`, via a call to `asyncio.ensure_future`, to
manage a (potentially long running) OS process. The `watchDo` task
listens, in an `FSWatcher.watchForFileSystemEvents` loop, for any file
system changes which might be happening, `reStart`ing the `taskRunner`
task on any such changes.

The `taskRunner` task starts by sleeping, during which time the
`taskRunner` task can be cancelled and `reStart`ed (by the `watchDo`
task). This short timeout period of cancel-able sleep acts as a debouncing
timer. It allows the `watchDo` task to frequently `reStart` the
`taskRunner` task without actually running the external OS process until
any nearly simultaneous file system changes have stopped.

If the `taskRunner` is not cancelled during the sleep, the `taskRunner`
starts the OS process, using a call to `asyncio.create_subprocess_exec`,
and then creates two further `asyncio.Tasks`, `captureStdout` and
`captureRetCode`, to manage the process's output as well as to wait for
the process's return code.

Once an external OS process has been started, any `reStart` requests from
the `watchDo` task, signals the `captureStdout` task to stop listening for
the process's stdout, and then sends a `SIGHUP` signal to the process
(which *must* respond by gracefully exiting). The `watchDo` task then
`wait`s on the `taskRunner` task to finish before creating a new
`taskRunner` task (and potentially repeating this cycle).

The `main` `cpawd` task, can at any time request that the `runTasks` task
shutdown. To shutdown, the `runTasks` task first signals all of the
`watchDo` `FSWatcher.watchForFileSystemEvents` loops to stop watching for
file system events. Then the `runTasks` task signals all running
`taskRunners` to stop.

----

In this interaction diagram, each `asyncio.Task` is represented by the
function which the task runs. The `OSproc` thread is an external OS
process, which is the ultimate "task" of a given watch-do task.

```mermaid

sequenceDiagram
  participant main
  participant runTasks
  participant watchDo
  participant taskRunner
  participant captureRetCode
  participant captureStdout
  participant OSproc

  activate main
  main-->>runTasks: run

  activate runTasks
  runTasks-->>watchDo: create_task

  activate watchDo
  Note over watchDo,OSproc: running (one watchDo for each watch-do task) ...
  watchDo-->>watchDo: reStart

  watchDo-->>watchDo: stopTaskProc
  Note over watchDo,OSproc: no task/proc running so stopTaskProc does nothing

  watchDo-->>taskRunner: ensure_future

  activate taskRunner
  taskRunner-->>taskRunner: sleep
  Note over taskRunner: a watchDo reStart<br/>at this point<br/>can cancel<br/>taskRunner<br/>while sleeping
  taskRunner-->>OSproc: exec
  activate OSproc
  taskRunner-->>captureStdout: wait on created task
  activate captureStdout
  taskRunner-->>captureRetCode: wait on created task
  activate captureRetCode

  OSproc-->>captureStdout: stdout
  OSproc-->>captureStdout: stdout
  OSproc-->>captureStdout: stdout

  Note over watchDo: file system<br/>change detected
  watchDo-->>watchDo: reStart
  watchDo-->>watchDo: stopTaskProc
  watchDo-->>OSproc: send SIGHUP
  OSproc-->>captureRetCode: finished
  deactivate OSproc
  captureRetCode-->>taskRunner: finished
  deactivate captureRetCode
  watchDo-->>captureStdout: continueCapturingStdout = False
  captureStdout-->>taskRunner: finished
  deactivate captureStdout
  watchDo-->>taskRunner: wait
  taskRunner-->>watchDo: done
  deactivate taskRunner

  watchDo-->>taskRunner: ensure_future
  activate taskRunner
  Note over taskRunner,OSproc:  new taskRunner starts ...
  taskRunner-->>watchDo: done
  deactivate taskRunner

  main-->>runTasks: shutdown

  runTasks-->>watchDo: stop listening for<br/>file system events

  runTasks-->>watchDo: stop debouncing timers
  watchDo-->>watchDo: stopTaskProc

  watchDo-->>runTasks: done
  deactivate watchDo

  runTasks-->>main: done
  deactivate runTasks

  deactivate main
```

----

"""

# Use psutil.pids() (returns list of pids) to check if the task's pid is
# still running.

import asyncio
import logging
import os
import signal

from cputils.debouncingTaskRunner import FileLogger, DebouncingTaskRunner
from cputils.fsWatcher import getMaskName, FSWatcher

logger = logging.getLogger("taskRunner")

watchers         = []
debouncingTimers = []

async def watchDo(aTaskName, aTask) :
  """ Setup and manage the watches, and then run the task's command using
  the DebouncingTimer whenever a change is detected in a watched directory
  or file. """

  logger.debug("Starting watchDo for {}".format(aTaskName))

  if 'env' in aTask :
    for aKey, aValue in aTask['env'].items() :
      os.environ[aKey] = aValue

  aWatcher = FSWatcher(logger)
  watchers.append(aWatcher)
  taskLog  = FileLogger(aTask['logFilePath'], 5)
  await taskLog.open()
  aTimer   = DebouncingTaskRunner(1, aTaskName, aTask, taskLog, signal.SIGHUP)
  debouncingTimers.append(aTimer)

  # add watches
  asyncio.create_task(aWatcher.managePathsToWatchQueue())
  for aWatch in aTask['watch'] :
    await aWatcher.watchARootPath(aWatch)

  # Ensure the task is run at least once
  logger.debug("First run of taskRunner for {}".format(aTaskName))
  await aTimer.reStart()

  # watch and run cmd
  if 'runOnce' not in aTask :
    async for event in aWatcher.watchForFileSystemEvents() :
      logger.debug("File system event mask {} for file [{}] for task {}".format(
        getMaskName(event.mask), event.name, aTaskName
      ))
      await aTimer.reStart()

async def stopTasks() :
  """Stop all watch-do tasks"""

  logger.info("Stopping all tasks")

  for aWatcher in watchers :
    aWatcher.stopWatchingFileSystem()

  for aTimer in debouncingTimers :
    await aTimer.stopTaskProc()
    await aTimer.cancelTimer()

  logger.debug("All tasks Stoped")

shutdownTasks = asyncio.Event()
async def waitForShutdown() :
  """Wait for the shutdown event and then stop all watch-do tasks"""

  logger.debug("waiting for eventual shutdown event")
  await shutdownTasks.wait()
  logger.debug("got shutdown")
  await stopTasks()
  logger.debug("shutdown")

async def runTasks(config) :
  """ Walk through the list of watch-do tasks and create an `asyncio.Task`
  for each task, using an invocation of the `watchDo` method to wrap each
  task. Since these tasks are not Python-CPU bound, they will essentially
  "run" in parallel. """

  for aTaskName, aTask in config['tasks'].items() :
    asyncio.create_task(watchDo(aTaskName, aTask))
  await waitForShutdown()
