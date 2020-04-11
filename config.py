'''
@Descripttion:
@version:
@Author: wangshiwen@36719
@Date: 2019-10-02 15:42:57
@LastEditors: wangshiwen@36719
@LastEditTime: 2020-02-18 14:41:32
'''
import os
from datetime import timedelta
basedir = os.path.abspath(os.path.dirname(__file__))


class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev')
    SQLALCHEMY_COMMIT_ON_TEARDOWN = True
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOADS_DEFAULT_DEST = os.getenv('CONTROLLER_REPOSITORY', os.path.abspath(os.path.join(basedir, '../repository')))
    UPLOADED_BLADED_DEST = UPLOADS_DEFAULT_DEST
    # UPLOADED_SYMBOL_DEST = UPLOADS_DEFAULT_DEST
    # UPLOADED_XML_DEST = UPLOADS_DEFAULT_DEST
    UPLOADS_CONTROLLER_SRC = os.getenv('CONTROLLER_POSITION1', os.path.join(UPLOADS_DEFAULT_DEST, '../controller'))
    CALCULATION_DEST = os.getenv('CALCULATION_POSTION', os.path.abspath(os.path.join(basedir, '../calculation')))
    SEND_FILE_MAX_AGE_DEFAULT = timedelta(seconds=1)


class DevelopmentConfig(Config):
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = os.getenv('DEV_DATABASE_URL', 'sqlite:///' + os.path.join(basedir, 'instance', 'app.db'))
    SQLALCHEMY_TRACK_MODIFICATIONS = False


class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = os.getenv('TEST_DATABASE_URL', 'sqlite:///' + os.path.join(basedir, 'instance', 'app.db'))


class ProductionConfig(Config):
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL', 'sqlite:///' + os.path.join(basedir, 'instance', 'app.db'))


config = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'production': ProductionConfig,

    'default': DevelopmentConfig
}
