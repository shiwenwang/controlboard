from flask import (Blueprint, render_template, redirect, request,
                   url_for, current_app, jsonify)
from flask_login import current_user, login_required
from app.models import load_user, Task
from app.forms import NewTaskForm, EditTaskForm, DeleteTaskForm
from app import usets, db
from app.extend.git import git_init, git_commit_push, git_remove_push, git_exists
from app.extend.symbol import XML
from app.extend.bladed import Bladed

import os
import shutil
import logging
from collections import OrderedDict
from datetime import date

main = Blueprint('main', __name__)


@main.route('/', methods=['GET', 'POST'])
@main.route('/index', methods=['GET', 'POST'])
@login_required
def index():
    user = load_user(current_user.get_id())
    tasks_amount = len(Task.query.filter_by(user_id=user.id).all())

    # delete 必须写在前面，避免select的影响
    delete_task_form = DeleteTaskForm()
    if delete_task_form.delete_submit.data and delete_task_form.validate():
        delete_task(user, delete_task_form)
        logging.log(
            logging.INFO, f"Deleted {delete_task_form.taskname.data} by {user.realname}")
        return redirect(url_for('main.index'))

    controller_tree = get_controller_tree()
    new_task_form = NewTaskForm()
    set_choices(new_task_form, request, controller_tree)
    if new_task_form.create_submit.data and new_task_form.validate():
        create_new_task(user, new_task_form)
        logging.log(
            logging.INFO, f"Created {new_task_form.taskname.data} by {user.realname}")
        return redirect(url_for('main.index'))

    edit_task_form = EditTaskForm()
    set_choices(edit_task_form, request, controller_tree)
    if edit_task_form.modify_submit.data and edit_task_form.validate():
        update_task(user, edit_task_form)
        logging.log(
            logging.INFO, f"Updated {edit_task_form.taskname.data} by {user.realname}")
        return redirect(url_for('main.index'))

    return render_template('index.html', title='主页', user=user, tasks_amount=tasks_amount,
                           new_task_form=new_task_form,
                           edit_task_form=edit_task_form,
                           delete_task_form=delete_task_form,
                           controller_tree=controller_tree
                           )


def create_new_task(user, new_task_form):
    """新建任务

    Arguments:
        user {User} -- 当前用户
        new_task_form {FlaskForm} -- 新建任务表单
    """
    task_name = new_task_form.taskname.data.strip()
    cfg = current_app.config
    root_destination = cfg.get('UPLOADS_DEFAULT_DEST')
    isgitted = new_task_form.add_to_git.data

    git_path = os.path.abspath(os.path.join(root_destination, user.username))
    if not git_exists(git_path):
        shutil.rmtree(git_path)  # 如果文件夹存在将清空
        git_init(git_path, user.username, isgitted, newfolder=task_name)  # 初始化

    saved_files = files_save(new_task_form, user, task_name)

    if not isgitted:
        gitignore_path = os.path.join(git_path, '.gitignore')
        with open(gitignore_path, 'a+') as f:
            f.write(f'\n{task_name}/')

    git_commit_push(git_path, f"Created task: {task_name}")  # 添加并提交文件
    local_bladed_path = os.path.join(root_destination, user.username,
                                     task_name, new_task_form.bladed.data.filename)

    task = Task(name=task_name,
                status="New",
                bladed_version=Bladed(local_bladed_path).version,
                user_id=user.id,
                isgitted=int(isgitted),
                bladed_filename=saved_files['bladed'],
                xml_filename="" if saved_files['ctrl'] is None else saved_files['ctrl']['xml'],
                dll_filename="" if saved_files['ctrl'] is None else saved_files['ctrl']['dll'],
                controller_src="" if saved_files['ctrl'] is None else saved_files['ctrl']['src']
                )

    db.session.add(task)
    db.session.commit()


def update_task(user, edit_task_form):
    """更新任务

    Arguments:
        user {User} -- 当前用户
        edit_task_form {FlaskForm} -- 任务编辑表单
    """
    cfg = current_app.config
    root_destination = cfg.get('UPLOADS_DEFAULT_DEST')

    task_name = edit_task_form.taskname.data
    task = Task.query.filter_by(name=task_name).first()
    file_updated = False
    commit_str = [f"Updated task: {task_name}"]
    if task is not None:
        saved_files = files_save(edit_task_form, user, task_name, task)

        if saved_files['bladed'] is not None:
            file_updated = True
            local_bladed_path = os.path.join(root_destination, user.username,
                                             task_name, edit_task_form.bladed.data.filename)
            task.bladed_version = Bladed(local_bladed_path).version
            task.bladed_filename = saved_files['bladed']
            commit_str.append("重新上传Bladed模型（覆盖旧文件）。")
        if saved_files['ctrl'] is not None:
            file_updated = True
            task.xml_filename = saved_files['ctrl']['xml']
            task.dll_filename = saved_files['ctrl']['dll']
            task.controller_src = saved_files['ctrl']['src']
            commit_str.append("重新上传控制器文件（覆盖旧文件）。")

    db.session.commit()
    git_path = os.path.abspath(os.path.join(root_destination, user.username))
    if file_updated and task and task.isgitted:
        git_commit_push(git_path, ", ".join(commit_str)
                        if commit_str else "一次滞后提交。")


def delete_task(user, delete_task_form):
    """删除任务

    Arguments:
        user {User} -- 用户
        delete_task_form {FlaskForm} -- 删除任务表单
    """
    task_name = delete_task_form.taskname.data
    task = Task.query.filter_by(name=task_name).first()
    cfg = current_app.config
    destination = os.path.abspath(os.path.join(
        cfg.get('UPLOADS_DEFAULT_DEST'), user.username, task_name))
    git_path = os.path.abspath(os.path.join(
        cfg.get('UPLOADS_DEFAULT_DEST'), user.username))

    if task is not None:
        db.session.delete(task)
        db.session.commit()

    if delete_task_form.delete_files.data:
        files_to_rm = []
        for f in os.listdir(destination):
            if os.path.splitext(f)[-1] in ['.dll', '.ini', '.xml', '.$pj', 'prj']:
                files_to_rm.append('/'.join([task_name, f]))
        if task.isgitted:
            git_remove_push(git_path, files_to_rm,
                            f"Deleted task: {task_name}")
        if os.path.isdir(destination):
            shutil.rmtree(destination)


def controller_folder_walk(folder, tree):
    """遍历控制器文件夹，返回目录json关系树，树叶为控制器文件

    Arguments:
        folder {[type]} -- [description]
        tree {[type]} -- [description]
    """
    dirs = [d for d in os.listdir(
        folder) if os.path.isdir(os.path.join(folder, d))]

    for d in dirs:
        files = [f for f in os.listdir(os.path.join(folder, d))
                 if os.path.isfile(os.path.join(folder, d, f)) and os.path.splitext(f)[-1] in ['.dll', '.xml', '.ini']]
        if files:
            tree[d] = files
            continue
        tree[d] = {}
        controller_folder_walk(os.path.join(folder, d), tree[d])


def get_controller_tree():
    controller_root = current_app.config.get('UPLOADS_CONTROLLER_SRC')
    controller_tree = OrderedDict()
    controller_folder_walk(controller_root, controller_tree)
    return controller_tree


def set_choices(form, rqst, ctrl_tree):
    if rqst.method == "GET":
        a, b, c = 0, 0, 0
        turbine_model_dict = ctrl_tree[list(ctrl_tree.keys())[a]]
        blade_model_dict = turbine_model_dict[list(
            turbine_model_dict.keys())[b]]
        tower_type_dict = blade_model_dict[list(blade_model_dict.keys())[c]]
    else:
        a, b, c = (rqst.form.get('turbine_platform'),
                   rqst.form.get('turbine_model'),
                   rqst.form.get('blade_model')
                   )
        turbine_model_dict = ctrl_tree[a]
        blade_model_dict = turbine_model_dict[b]
        tower_type_dict = blade_model_dict[c]

    form.turbine_platform.choices = [(d, d) for d in ctrl_tree.keys()]
    form.turbine_model.choices = [(d, d) for d in turbine_model_dict.keys()]
    form.blade_model.choices = [(d, d) for d in blade_model_dict.keys()]
    form.tower_type.choices = [(d, d) for d in tower_type_dict.keys()]


def files_save(form, user, taskname, task=None):
    uset_bladed, = usets
    saved_files = {'bladed': None, 'ctrl': None}

    target_dir = os.path.abspath(os.path.join(
        uset_bladed.config.destination, user.username, taskname))

    if form.bladed.data:
        """上传Bladed文件
        """
        delete_file(target_dir, ['.$pj', '.prj'])
        uset_bladed.save(
            form.bladed.data, folder=target_dir, name=form.bladed.data.filename)
        saved_files['bladed'] = form.bladed.data.filename

    if form.turbine_platform.data and form.turbine_model.data and \
            form.blade_model.data and form.tower_type.data:
        """将控制器文件从原位置复制到Git仓库目录下
        """
        controller_root = current_app.config.get('UPLOADS_CONTROLLER_SRC')
        turbine_platform_item = form.turbine_platform.data
        turbine_model_item = form.turbine_model.data
        blade_model_item = form.blade_model.data
        tower_type_item = form.tower_type.data
        controller_src = os.path.abspath(os.path.join(controller_root, turbine_platform_item, turbine_model_item,
                                                      blade_model_item, tower_type_item))

        if task is None or (task is not None and task.controller_src != controller_src):
            """ （新建任务）复制文件<task is None>
                （编辑任务）如果任务的控制器原路径不同于当前，复制新的控制器并覆盖原来的，
                否则，忽略。
            """
            saved_files['ctrl'] = {}
            delete_file(target_dir, ['.dll', '.xml', '.ini'])
            for d in os.listdir(controller_src):
                file_ext = os.path.splitext(d)[-1]

                if file_ext in ['.dll', '.xml', '.ini']:
                    shutil.copy(os.path.join(controller_src, d), target_dir)
                    update_item = {
                        'dll': d} if file_ext == '.dll' else {'xml': d}
                    saved_files['ctrl'].update(update_item)
                    saved_files['ctrl']['src'] = controller_src

            if saved_files['ctrl']:
                readme_txt = os.path.join(target_dir, 'README.txt')
                if task is None:
                    with open(readme_txt, 'w') as f:
                        spec = (f"==== D0: ({date.today().isoformat()}) =====\n"
                                 "├─原始控制器:\n"
                                f"    ├─{saved_files['ctrl']['dll']}\n"
                                f"    └─{saved_files['ctrl']['xml']}\n\n")
                        f.write(spec)
                else:
                    with open(readme_txt, 'a') as f:
                        spec = (f"==== 更新控制器: ({date.today().isoformat()}) =====\n"
                                 "├─新版控制器:\n"
                                f"    ├─{saved_files['ctrl']['dll']}\n"
                                f"    └─{saved_files['ctrl']['xml']}\n\n")
                        f.write(spec)

    return saved_files


def delete_file(folder, exts):
    if not os.path.isdir(folder):
        return
    for f in os.listdir(folder):
        if os.path.splitext(f)[-1].lower() in exts:
            os.remove(os.path.join(folder, f))


@main.route('/compare/contrast', methods=['GET', 'POST'])
def contrast():
    if request.method == "POST":
        file1_text = request.files.getlist("xml-files")[0].read().decode()
        file2_text = request.files.getlist("xml-files")[1].read().decode()
        xml = XML()
        xml1_data = xml.parse_string(file1_text)
        xml2_data = xml.parse_string(file2_text)
        diff = find_diff(xml1_data, xml2_data)

        data = {'xml1': xml1_data, 'xml2': xml2_data, 'diff': diff}
        return jsonify(data)

    return jsonify({})


@main.route('/compare')
def compare():
    return render_template('compare.html', title="compare")


def find_diff(data1, data2):
    import pandas as pd
    set1 = set(data1.keys())
    set2 = set(data2.keys())
    for name in set.union(set1.difference(set2), set2.difference(set1)):
        if name not in data1.keys():
            data1[name] = '-' if 'P_' in name else {}
        if name not in data2.keys():
            data2[name] = '-' if 'P_' in name else {}

    diff = [k for k, v in data1.items() if (isinstance(v, str) and v != data2[k]) or
            (isinstance(v, pd.DataFrame) and not all(v == data2[k]))]
    diff.extend(list(set.union(set1.difference(set2), set2.difference(set1))))

    return diff
