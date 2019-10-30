from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed, FileRequired

from wtforms import (StringField, PasswordField, BooleanField, SubmitField,
                     SelectField, RadioField)
from wtforms.validators import DataRequired, Email, EqualTo, ValidationError

from app.models import User
from app import usets

import sqlite3
import os

here = os.path.dirname(__file__)


def employees_query(items_to_find=[], **given_values):
    """

    Returns:
        ((...),(...),(...),)
    """
    lst = []
    if not isinstance(items_to_find, list):
        lst.append(items_to_find)
        items_to_find = lst
    find_items = ', '.join(items_to_find) if items_to_find else '*'
    where_stms = ' AND '.join([f"{k}='{v}'" for k, v in given_values.items()])
    if where_stms:
        where_stms = 'where ' + where_stms
    db_path = os.path.abspath(os.path.join(here, './static/data/employees.db'))
    db_czdp = sqlite3.connect(db_path)
    cr = db_czdp.cursor()
    cr.execute(f"SELECT {find_items} FROM employees {where_stms}")
    result = cr.fetchall()
    db_czdp.close()
    return tuple(zip(*result))


class LoginForm(FlaskForm):
    username = StringField(validators=[DataRequired()])
    password = PasswordField(validators=[DataRequired()])
    remember = BooleanField()
    login_submit = SubmitField()


class SendEmail(FlaskForm):
    email = StringField(validators=[DataRequired(), Email(message='邮箱不合法。')])
    submit = SubmitField()
    emails = employees_query('电子邮箱')[0]

    def validate_email(self, email):
        if self.email.errors:
            raise ValidationError()

        if self.email.data not in self.emails:
            raise ValidationError('请输入注册使用的邮箱。')


class RegistrationForm(FlaskForm):
    username = StringField(validators=[DataRequired()])
    email = StringField(validators=[DataRequired(), Email(message='邮箱不合法。')])
    password = PasswordField(validators=[DataRequired()])
    password2 = PasswordField(
        validators=[DataRequired(), EqualTo('password', message='两次密码输入不一致。')])
    register_submit = SubmitField()
    employees = employees_query(['OA', '电子邮箱'])

    def validate_username(self, username):
        if not str(username.data).isdigit():
            raise ValidationError('用户名不合法，请使用OA号。')
        if username.data not in self.employees[0]:
            oa = username.data
            raise ValidationError(f"{oa}不允许注册。")
        user = User.query.filter_by(username=username.data).first()
        if user is not None:
            raise ValidationError('此OA号已被注册。')

    def validate_email(self, email):
        if self.email.errors:
            raise ValidationError()

        if self.email.data not in self.employees[1]:
            raise ValidationError('请使用正确的公司邮箱。')

        username_id = self.employees[0].index(self.username.data)
        email_id = self.employees[1].index(email.data)
        if username_id != email_id:
            raise ValidationError('OA和邮箱不匹配。')
        user = User.query.filter_by(email=email.data).first()
        if user is not None:
            raise ValidationError('该邮箱已被注册。')

    def clear_errors(self):
        self.username.errors = ()
        self.email.errors = ()
        self.password2.errors = ()


class ResetPassWordForm(FlaskForm):
    old_password = PasswordField(validators=[DataRequired()])
    new_password = PasswordField(validators=[DataRequired()])
    new_password2 = PasswordField(
        validators=[DataRequired(), EqualTo('new_password', message='两次密码输入不一致。')])
    reset_submit = SubmitField()


class MainForm(FlaskForm):
    search = StringField()
    all_task_switch = BooleanField()


class NewTaskForm(FlaskForm):
    from flask import current_app

    bladed, symbol, xml = usets
    taskname = StringField(validators=[DataRequired()])
    f_bladed = FileField(validators=[FileAllowed(bladed), FileRequired()])
    f_xml = FileField(validators=[FileAllowed(bladed), FileRequired()])

    symbols_dir = current_app.config.get('UPLOADS_TEMPL_DEST')
    f_symbol_choices = [(0, "未选择")]
    for file in os.listdir(symbols_dir):
        f_symbol_choices.append(file.splitext()[0])

    f_symbol = SelectField(choices=f_symbol_choices, default=0, coerce=int)
    save_submit = SubmitField()

    # def __init__(self):
    #     self.read_symbol_files()
    #
    # @classmethod
    # def read_symbol_files(cls):
    #     cfg = current_app.config
    #     symbol_dir = cfg.get('UPLOADS_TEMPL_DEST')
    #     symbol_choices = []
    #     for i, file in enumerate(os.listdir(symbol_dir)):
    #         symbol_choices.append((i, file.split('.')[0]))
    #
    #     cls.f_symbol = SelectField(choices=symbol_choices,
    #                                default=0,
    #                                coerce=int)

    def files_save(self, _usets):
        bladed, symbol, xml = _usets
        local_bladed_path = os.path.join(bladed.config.destination, self.f_bladed.data.filename)
        if os.path.isfile(local_bladed_path):
            os.remove(local_bladed_path)
        bladed_filename = bladed.save(self.f_bladed.data, name=self.f_bladed.data.filename)

        return bladed_filename
