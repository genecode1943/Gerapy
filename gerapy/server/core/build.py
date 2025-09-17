import sys
import os
import glob
import tempfile
import shutil
import errno

from gerapy import get_logger
from gerapy.cmd.init import PROJECTS_FOLDER
from gerapy.server.core.config import config
from os.path import join
from subprocess import check_call

logger = get_logger(__name__)


def build_project(project):
    """
    build project
    """
    egg = build_egg(project)
    logger.info('✅ successfully build project %s to egg file %s', project, egg)
    return egg


_SETUP_PY_TEMPLATE = \
    '''# Automatically created by: gerapy
from setuptools import setup, find_packages
setup(
    name='%(project)s',
    version='1.0',
    packages=find_packages(),
    entry_points={'scrapy':['settings=%(settings)s']},
)'''


def retry_on_eintr(function, *args, **kw):
    """Run a function and retry it while getting EINTR errors"""
    while True:
        try:
            return function(*args, **kw)
        except IOError as e:
            if e.errno != errno.EINTR:
                raise


def build_egg(project):
    """
    build project to egg file
    :param project:
    :return: absolute path of egg file
    """
    work_path = os.getcwd()
    try:
        # 项目根目录
        path = os.path.abspath(join(os.getcwd(), PROJECTS_FOLDER))
        project_path = join(path, project)

        if not os.path.exists(project_path):
            raise FileNotFoundError(f"❌ Project path not found: {project_path}")

        logger.info("⚙️  running egg build command in %s", project_path)
        os.chdir(project_path)

        # 生成 setup.py
        settings = config(project_path, 'settings', 'default')
        setup_file_path = join(project_path, 'setup.py')
        create_default_setup_py(setup_file_path, settings=settings, project=project)

        # 临时目录
        d = tempfile.mkdtemp(prefix='gerapy-')
        o = open(os.path.join(d, 'stdout'), 'wb')
        e = open(os.path.join(d, 'stderr'), 'wb')

        # 打包 egg
        retry_on_eintr(
            check_call,
            [sys.executable, 'setup.py', 'clean', '-a', 'bdist_egg', '-d', d],
            stdout=o,
            stderr=e
        )
        o.close()
        e.close()

        eggs = glob.glob(os.path.join(d, '*.egg'))
        if not eggs:
            raise FileNotFoundError(f"❌ No egg built in {d}, check stderr log.")

        egg = eggs[0]

        # 删除原有 egg
        old_egg = find_egg(project_path)
        if old_egg:
            try:
                os.remove(old_egg)
                logger.info("🗑️  removed old egg: %s", old_egg)
            except Exception as ex:
                logger.warning("⚠️  failed to remove old egg %s: %s", old_egg, ex)

        # 移动新 egg
        target_egg = os.path.join(project_path, os.path.basename(egg))
        shutil.move(egg, target_egg)
        logger.info("✅ new egg moved to %s", target_egg)

        return target_egg

    except Exception as e:
        logger.error("❌ error occurred in build_egg: %s", e, exc_info=True)
    finally:
        os.chdir(work_path)


def find_egg(path):
    """
    find egg from path
    """
    if not os.path.exists(path):
        logger.warning("⚠️  find_egg: path not found %s", path)
        return None

    for name in os.listdir(path):
        if name.endswith('.egg'):
            return os.path.join(path, name)

    logger.warning("⚠️  find_egg: no egg found in %s", path)
    return None


def create_default_setup_py(path, **kwargs):
    """
    create setup.py file to path
    """
    if os.path.exists(path):
        logger.debug('setup.py file already exists at %s', path)
    else:
        file = _SETUP_PY_TEMPLATE % kwargs
        logger.debug('setup.py content:\n%s', file)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(file)
        logger.debug('✅ successfully created setup.py file at %s', path)
