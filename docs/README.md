# ComputePods Asynchronous Watch-Do tools

This tool uses the [Python
asyncio](https://docs.python.org/3/library/asyncio.html),
[asyncinotify](https://asyncinotify.readthedocs.io/en/latest/) and
[aiofiles](https://github.com/Tinche/aiofiles) libraries to monitor a
number of watch-do tasks in "parallel".

Each watch-do task consists of a number of directories and/or files to be
watched for changes. On any change, a corresponding task is run, the
output captured and appended to a long running log file associated with
that task.

Each watch-do task should be provided with a `projectDir`, a list of
watches (directories/files relative to the `projectDir`), and a command.
You can use standard Python
[str.format](https://docs.python.org/3/library/stdtypes.html#str.format)
notation to format the command. The command string format will be provided
with the dict of configured tasks.

Each watch-do task will automatically be provided a `workDir` as well as a
`logFile` (opened on the path `logFilePath`), which will be located in
that task's `workDir`. On Linux, by default a task's `workDir` will be
located in the `/tmp` directory, and so will be automatically removed on
each reboot.

## Installation

This python tool has *not* (yet) been uploaded to
[pypi.org](https://pypi.org/).

So to install it you need to use:

```
pip install git+https://github.com/computePods/asyncWatchDo/
```

([see Examples 5. Install a project from
VCS](https://pip.pypa.io/en/stable/cli/pip_install/#examples)) **or**

```
pipx install git+https://github.com/computePods/asyncWatchDo/
```

([see installing from source
control](https://pypa.github.io/pipx/#installing-from-source-control)).

## `cpawd` command

The `cpawd` command looks for its configuration in a `cpawdConfig.yaml`
[YAML file](https://en.wikipedia.org/wiki/YAML) located in the directory
in which the `cpawd` is started. The `cpawd` command takes three optional
arguments, `--verbose` (to report the loaded configuration), `--config`
(to layer on additional configuration files), and `--help`.

```
dev:~/dev/computePods/asyncWatchDo$ cpawd --help
usage: cpawd [-h] [-c CONFIG] [-v | --verbose | --no-verbose]
             [-d | --debug | --no-debug] [-p PAGER]

Asynchronously watch multiple directories and perform actions on changes.

optional arguments:
  -h, --help            show this help message and exit
  -c CONFIG, --config CONFIG
                        overlay configuration from file
  -v, --verbose, --no-verbose
                        show the loaded configuration (default: False)
  -d, --debug, --no-debug
                        provide debugging output (default: False)
  -p PAGER, --pager PAGER
                        pager to use in task list (default=moar)
```
## Configuration file

The `cpawdConfig.yaml` file expects three sections:

- **tasks**: is a dict of watch-do task descriptions, each of which
  is itself a dict with the keys:

    - **cmd** : is a list of command line arguments which will be run
      (using exec) whenever any change is detected. Arguments can use the
      python `str.format` to dynamically add information from the tasks
      dictionary. You can use this to ensure commands for one task, can
      use information, such as `workDir`, from any other configured task
      (see example below).

    - **projectDir** : provides a single main directory from which all of
      the watch paths are expected to be located relatively. If no
      `projectDir` is provided, it will be assigned to the `workDir`.

    - **watch** : is a list of paths, relative to the projectDir, to be
      (recursively) watched for changes. The `watch` paths, can,
      optionally, be specified with either a leading `~` or `/`. Watch
      paths with leading `~` will be relative to the user's home
      directory. Watch paths with leading `/` are assumed to be absolute
      paths and are not altered. Watch paths with no leading `~` or `/`
      are assumed to be relative to the projectDir.

    - **runOnce** : is a key which, if it exists, ensures the command is
      only run once (and is never restarted on file system events). You
      can use this for any command which provides its own file system
      watch abilities.

    - **toolTips** : is a string which will be echoed to the user. You can
      use this, for example, to inform the user of the configured URL
      provided by a web-server task.

    All other keys will be provided to the `str.format` when expanding
    either the command arguments or the toolTips (see the example below).

- **verbose**: is a Boolean which if `True`, will report the loaded
  configuration. The default is `False`.

- **workDir**: is a dict with the keys `baseDir` and `prefix`. This
  `workDir` is used to specify the base `workDir` for all of the work-do
  task's individual `workDirs`. The base `workDir` will be located in the
  `baseDir` and will have the name consisting of the `prefix` appended
  with the date and time the `cpawd` command was started. The default
  `baseDir` is `/tmp` and the default `prefix` is `cpawd`.

### Example

An example `cpawdConfig.yaml` configuration file might be:

```yaml
tasks:
  webServer:
    runOnce: true
    toolTips: "http://localhost:{webServer[port]}"
    port: "8008"
    watch:
      - html
    cmd:
      - cphttp
      - -v
      - -l
      - debug
      - p
      - "{webServer[port]}"
      - -d
      - "{webServer[workDir]}/html"
      - -w
      - "{webServer[workDir]}/html"

  computePods:
    projectDir: ~/dev/computePods/computePods.github.io
    watch:
      - docs
    cmd:
      - mkdocs
      - --verbose
      - --site-dir
      - "{webServer[workDir]}/html"

  pythonUtils:
    projectDir: ~/dev/computePods/pythonUtils
    watch:
      - cputils
      - tests
    cmd:
      - mkdocs
      - --verbose
      - --site-dir
      - "{webServer[workDir]}/html/pythonUtils"

  interfaces:
    projectDir: ~/dev/computePods/interfaces
    watch:
      - docs
      - interaces
    cmd:
      - mkdocs
      - --verbose
      - --site-dir
      - "{webServer[workDir]}/html/interfaces"
```

**Notes**:

- The `{webServer[workDir]}` in each of the above `cmd` keys will be
dynamically replaced (using the `str.format` function) to the value of the
`webServer` watch-do task's `workDir`.

- You can add your own keys in each of the tasks (for example the `port`
key in the example above). These keys will also be available to the
command or toolTips `str.format` function invocation.

- Since we have not provided either of the `verbose` or `workDir`
sections, they will automatically default to `False` and
`/tmp/cpawd-YYYYMMDD-HHMMSS`.

- This example `cpawdConfig.yaml` file implements a simple
multi-repository `mkdocs` tool, similar to
[`monorepo`](https://github.com/backstage/mkdocs-monorepo-plugin). However
by using `cpawd` to implement a multi-repository `mkdocs` tool, the
`mkdocs` invocations in each repository are *completely* separate from
each other. (Alas, when using `monorepo` to implement multi-repository
documentation, the `monorepo` extension interferes with many of the other
`mkdocs` extensions).

## Output

When run, the `cpawd` command will out put a list of the configured
toolTips and log files:

```
Tool tips:

webServer
  http://localhost:8008

---------------------------------------------------------------

Logfiles for each task:
webServer
  tail -f /tmp/cpawd-20210724-171805/webServer/command.log
  moar /tmp/cpawd-20210724-171805/webServer/command.log
computePods
  tail -f /tmp/cpawd-20210724-171805/computePods/command.log
  moar /tmp/cpawd-20210724-171805/computePods/command.log
pythonUtils
  tail -f /tmp/cpawd-20210724-171805/pythonUtils/command.log
  moar /tmp/cpawd-20210724-171805/pythonUtils/command.log
interfaces
  tail -f /tmp/cpawd-20210724-171805/interfaces/command.log
  moar /tmp/cpawd-20210724-171805/interfaces/command.log

---------------------------------------------------------------
```

This list of toolTips and log files is then followed by a "stream of
consciousness" list of tasks run.

If you copy and paste any of the log file commands (as above) in the 'tab'
of a terminal emulator, you will be able to watch the outputs of the
respective tasks as they are run.
