from flask import (Blueprint, render_template, redirect, request,
                   url_for, current_app, jsonify)
from flask_login import current_user, login_required
from app.models import load_user, Task
from app.forms import NewTaskForm, EditTaskForm, DeleteTaskForm
from app import usets, db
from app.extend.git import git_init, git_commit_push, git_remove_push, git_exists
from app.extend.symbol import XML, SymbolDB
from app.extend.bladed import Bladed

import os
import re
import json
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

    # git_path = os.path.abspath(os.path.join(root_destination, user.username))
    git_path = os.path.abspath(os.path.join(root_destination))
    if not git_exists(git_path):
        git_init(git_path, user.username, isgitted, newfolder=task_name)  # 初始化

    saved_files = files_save(new_task_form, user, task_name)

    if not isgitted:
        gitignore_path = os.path.join(git_path, '.gitignore')
        with open(gitignore_path, 'a+') as f:
            f.write(f'\n{task_name}/')

    git_commit_push(git_path, f"Created task: {task_name}")  # 添加并提交文件
    # local_bladed_path = os.path.join(root_destination, user.username,
    #                                  task_name, new_task_form.bladed.data.filename)
    local_bladed_path = os.path.join(root_destination, 
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
            # local_bladed_path = os.path.join(root_destination, user.username,
            #                                  task_name, edit_task_form.bladed.data.filename)
            local_bladed_path = os.path.join(root_destination, 
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
    # git_path = os.path.abspath(os.path.join(root_destination, user.username))
    git_path = os.path.abspath(os.path.join(root_destination))
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
    # destination = os.path.abspath(os.path.join(
    #     cfg.get('UPLOADS_DEFAULT_DEST'), user.username, task_name))
    destination = os.path.abspath(os.path.join(cfg.get('UPLOADS_DEFAULT_DEST'), task_name))
    # git_path = os.path.abspath(os.path.join(
    #     cfg.get('UPLOADS_DEFAULT_DEST'), user.username))

    git_path = os.path.abspath(cfg.get('UPLOADS_DEFAULT_DEST'))

    if task is not None:
        db.session.delete(task)
        db.session.commit()

    if delete_task_form.delete_files.data:
        files_to_rm = []
        if os.path.exists(destination):
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
    logging.log(logging.DEBUG, controller_root)
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

    # target_dir = os.path.abspath(os.path.join(
    #     uset_bladed.config.destination, user.username, taskname))
    
    target_dir = os.path.abspath(os.path.join(current_app.config.get("UPLOADS_DEFAULT_DEST"), taskname))

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
                    with open(readme_txt, 'w', encoding='utf-8') as f:
                        spec = (f"==== D0: ({date.today().isoformat()}) =====\n"
                                 "├─原始控制器:\n"
                                f"    ├─{saved_files['ctrl']['dll']}\n"
                                f"    └─{saved_files['ctrl']['xml']}\n\n")
                        f.write(spec)
                else:
                    with open(readme_txt, 'a', encoding='utf-8') as f:
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


@main.route('/utils')
def utils():
    return render_template('utils.html', title="Utils")


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


# @main.route('/xml_view')
# def xml_view():
#     return render_template('xml_view.html', title="view")



@main.route('/utils/compare', methods=['POST'])
def compare():
    file1_text = request.files.getlist("xml-files")[0].read().decode()
    file2_text = request.files.getlist("xml-files")[1].read().decode()
    xml = XML()
    xml1_data = xml.parse_string(file1_text)
    xml2_data = xml.parse_string(file2_text)
    diff = find_diff(xml1_data, xml2_data)

    data = {'xml1': xml1_data, 'xml2': xml2_data, 'diff': diff}
    return jsonify(data)


@main.route('/utils/parse', methods=['POST'])
def xml_parse():
    xml_file = request.files.get('xml-input')
    xml = XML()
    xml.parse_string(xml_file.read().decode())
    
    bladed_file = request.files.get('bladed-input')
    if bladed_file is not None:
        bladed = Bladed(bladed_file.read().decode())
    only_in_bladed = ['P_DMGT']

    symbols_value = {'params': [], 'filters': [], 'schedules': []}
    p_items, t_items, f_items, symbols_name = get_query_names(current_app, only_in_bladed)

    xml_values = {}
    for name in symbols_name.keys():
        if name in only_in_bladed:
            xml_values[name] = ""
            continue
        xml_values.update(xml.find(name))

    for name, value in xml_values.items():
        if 'P_' in name:
            symbols_value['params'].append({
                'name': f'<span class="name text-theme" data-toggle="tooltip" data-placement="right" title="'
                f'{p_items[name].at["Description_en_GB"] if name not in only_in_bladed and name in p_items.keys() else symbols_name[name]["description_zh"]}'
                f'">{name}</span>',
                'bladed_value': '-' if not symbols_name[name]['bladed'] or bladed_file is None else
                f'<input type="text" class="table-value-bladed text-primary" id="{name}-bladed" disabled value="{bladed.query(symbols_name[name]["bladed"])[1]}"'
                f'style="background-color:transparent;border:0;text-align:center;width:100px;">',
                'symbol_value': '-' if name in only_in_bladed else
                f'<input type="text" class="table-value text-primary" id="{name}-symbol" disabled value="{value}"'
                f'style="background-color:transparent;border:0;text-align:center;width:100px;" onchange="checkChanged()">',
                'description': symbols_name[name]["description_zh"]
            })
        if 'T_' in name:
            for index in value.index:
                symbols_value['schedules'].append({
                    'Name': f'<span class="name text-theme" data-toggle="tooltip" data-placement="right" title="'
                    f'{t_items[f"{name}0"].at["Description_en_GB"]}">{name}</span>',
                    'Enabled':
                        f'<input type="text" class="table-value enable-col  text-danger" id="{name}{index}-Enabled" disabled value="{value.at[0, "Enabled"]}"'
                        f'style="background-color:transparent;border:0;text-align:center;width:50px;" onchange="checkChanged()">',
                    'Display_Name': t_items[f'{name}{index}'].at["Display_Name"],
                    '0': '-' if '_0' not in value.columns else
                    f'<input type="text" class="table-value text-primary" id="{name}{index}-0" disabled value="{value.at[index, "_0"]}"'
                    f'style="background-color:transparent;border:0;text-align:center;width:100px;" onchange="checkChanged()">',
                    '1': '-' if '_1' not in value.columns else
                    f'<input type="text" class="table-value text-primary" id="{name}{index}-1" disabled value="{value.at[index, "_1"]}"'
                    f'style="background-color:transparent;border:0;text-align:center;width:100px;" onchange="checkChanged()">',
                    '2': '-' if '_2' not in value.columns else
                    f'<input type="text" class="table-value text-primary" id="{name}{index}-2" disabled value="{value.at[index, "_2"]}"'
                    f'style="background-color:transparent;border:0;text-align:center;width:100px;" onchange="checkChanged()">',
                    '3': '-' if '_3' not in value.columns else
                    f'<input type="text" class="table-value text-primary" id="{name}{index}-3" disabled value="{value.at[index, "_3"]}"'
                    f'style="background-color:transparent;border:0;text-align:center;width:100px;" onchange="checkChanged()">',
                    '4': '-' if '_4' not in value.columns else
                    f'<input type="text" class="table-value text-primary" id="{name}{index}-4" disabled value="{value.at[index, "_4"]}"'
                    f'style="background-color:transparent;border:0;text-align:center;width:100px;" onchange="checkChanged()">',
                    '5': '-' if '_5' not in value.columns else
                    f'<input type="text" class="table-value text-primary" id="{name}{index}-5" disabled value="{value.at[index, "_5"]}"'
                    f'style="background-color:transparent;border:0;text-align:center;width:100px;" onchange="checkChanged()">',
                    '6': '-' if '_6' not in value.columns else
                    f'<input type="text" class="table-value text-primary" id="{name}{index}-6" disabled value="{value.at[index, "_6"]}"'
                    f'style="background-color:transparent;border:0;text-align:center;width:100px;" onchange="checkChanged()">',
                    '7': '-' if '_7' not in value.columns else
                    f'<input type="text" class="table-value text-primary" id="{name}{index}-7" disabled value="{value.at[index, "_7"]}"'
                    f'style="background-color:transparent;border:0;text-align:center;width:100px;" onchange="checkChanged()">',
                    '8': '-' if '_8' not in value.columns else
                    f'<input type="text" class="table-value text-primary" id="{name}{index}-8" disabled value="{value.at[index, "_8"]}"'
                    f'style="background-color:transparent;border:0;text-align:center;width:100px;" onchange="checkChanged()">',
                    '9': '-' if '_9' not in value.columns else
                    f'<input type="text" class="table-value text-primary" id="{name}{index}-9" disabled value="{value.at[index, "_9"]}"'
                    f'style="background-color:transparent;border:0;text-align:center;width:100px;" onchange="checkChanged()">'
                })
        if 'F_' in name:
            for index in value.index:
                symbols_value['filters'].append({
                    'Name': f'<span class="name text-theme" data-toggle="tooltip" data-placement="right" title="'
                    f'{f_items[f"{name}0"].at["Description_en_GB"]}">{name}</span>',
                    'Enabled':
                    f'<input type="text" class="table-value enable-col text-danger" id="{name}{index}-Enabled" disabled value="{value.at[index, "Enabled"]}"'
                    f'style="background-color:transparent;border:0;text-align:center;width:50px;" onchange="checkChanged()">',
                    'Display_Name': str(index + 1),
                    'Numerator_Type': value.at[index, "Numerator_Type"],
                    'Denominator_Type': value.at[index, "Denominator_Type"],
                    'Numerator_TC': value.at[index, "Numerator_TC"],
                    'Denominator_TC': value.at[index, "Denominator_TC"],
                    'Numerator_Frequency':
                    f'<input type="text" class="table-value num-frequency-col text-primary" id="{name}{index}-Numerator_Frequency" disabled value="{value.at[index, "Numerator_Frequency"]}"'
                    f'style="background-color:transparent;border:0;text-align:center;width:100px;" onkeyup="equals(\'{name}{index}-Numerator_Frequency\', \'{name}{index}-Denominator_Frequency\')" onchange="checkChanged()">',
                    'Numerator_Damping_Ratio':
                    f'<input type="text" class="table-value text-primary" id="{name}{index}-Numerator_Damping_Ratio" disabled value="{value.at[index, "Numerator_Damping_Ratio"]}"'
                    f'style="background-color:transparent;border:0;text-align:center;width:100px;" onchange="checkChanged()">',
                    'Denominator_Frequency':
                    f'<input type="text" class="table-value den-frequency-col text-primary" id="{name}{index}-Denominator_Frequency" disabled value="{value.at[index, "Denominator_Frequency"]}"'
                    f'style="background-color:transparent;border:0;text-align:center;width:100px;" onkeyup="equals(\'{name}{index}-Denominator_Frequency\', \'{name}{index}-Numerator_Frequency\')" onchange="checkChanged()">',
                    'Denominator_Damping_Ratio':
                    f'<input type="text" class="table-value text-primary" id="{name}{index}-Denominator_Damping_Ratio" disabled value="{value.at[index, "Denominator_Damping_Ratio"]}"'
                    f'style="background-color:transparent;border:0;text-align:center;width:100px;" onchange="checkChanged()">',
                    'W0':
                    f'<input type="text" class="table-value text-primary" id="{name}{index}-W0" disabled value="{value.at[index, "W0"]}"'
                    f'style="background-color:transparent;border:0;text-align:center;width:100px;" onchange="checkChanged()">',
                    'Prewarping_Wc':
                    f'<input type="text" class="table-value text-primary" id="{name}{index}-Prewarping_Wc" disabled value="{value.at[index, "Prewarping_Wc"]}"'
                    f'style="background-color:transparent;border:0;text-align:center;width:100px;" onchange="checkChanged()">',
                })

    return jsonify(symbols_value)


def get_query_names(app, only_in_bladed):
    with app.open_instance_resource('name_mapping.json') as f:
        symbols_name = OrderedDict(json.load(f))

    symbols_db_path = os.path.join(app.instance_path, 'symbols.db')

    symbols = SymbolDB()
    symbols.load_db(symbols_db_path)
    symbols.connect()

    p_name = [p for p in symbols_name.keys() if 'P_' in p and p not in only_in_bladed]
    f_name = [p for p in symbols_name.keys() if 'F_' in p]
    t_name = [p for p in symbols_name.keys() if 'T_' in p]
    p_query = symbols.multi_query(p_name)
    f_query = symbols.multi_query(f_name)
    t_query = symbols.multi_query(t_name)
    symbols.close()

    t_items = handle_number_posx(t_name, t_query)
    f_items = handle_number_posx(f_name, f_query)

    return p_query, t_items, f_items, symbols_name


def handle_number_posx(names, _query):
    pattern = re.compile(r'\d+$')
    _items = {}
    for name in names:
        items = {k: v for k, v in _query.items() if pattern.sub("", k, 1) == name}
        items_sorted = sorted(items.items())
        fine_items = {pattern.sub("", item[0], 1) + str(i): item[1] for i, item in enumerate(items_sorted)}
        _items.update(fine_items)

    return _items


@main.route('/xml_view/download')
def xml_download():
    pass


@main.route('/utils/match/<keyword>', methods=['POST'])
def match(keyword):
    xml_file = request.files.get('xml-input')
    xml = XML()
    xml.parse_string(xml_file.read().decode())

    names = []
    if keyword:
        names = xml.query(keyword, name_only=True)

    return jsonify(names)


@main.route('/utils/search/<param>', methods=['POST'])
def search(param):
    xml_file = request.files.get('xml-input')
    xml = XML()
    xml.parse_string(xml_file.read().decode())

    symbols_value = {'params': [], 'filters': [], 'schedules': []}

    symbols_db_path = os.path.join(current_app.instance_path, 'symbols.db')

    pattern = re.compile(r'\d+$')
    symbols = SymbolDB()
    symbols.load_db(symbols_db_path)
    symbols.connect()
    queried = symbols.multi_query([param])
    symbols.close()

    # queried = {pattern.sub("", k, 1): v for k, v in queried.items()}
    items_sorted = sorted(queried.items())
    fine_items = {pattern.sub("", item[0], 1) + str(i): item[1] for i, item in enumerate(items_sorted)}

    xml_values = xml.find(param)
    value = xml_values[param]

    if 'P_' in param:
        symbols_value['params'].append({
            'name': f'<span class="name text-theme" data-toggle="tooltip" data-placement="right" title="'
            f'{queried[param].at["Description_en_GB"] if param in queried.keys() else param}">{param}</span>',
            'bladed_value': '-',
            'symbol_value':
            f'<input type="text" class="table-value text-primary" id="{param}-symbol" disabled value="{value}"'
            f'style="background-color:transparent;border:0;text-align:center;width:100px;">',
            'description': ""
        })
    if 'T_' in param:
        for index in value.index:
            symbols_value['schedules'].append({
                'Name': f'<span class="name text-theme" data-toggle="tooltip" data-placement="right" title="'
                f'{queried[param].at["Description_en_GB"] if param in queried.keys() else param}">{param}</span>',
                'Enabled':
                    f'<input type="text" class="table-value enable-col  text-danger" id="{param}{index}-Enabled" disabled value="{value.at[0, "Enabled"]}"'
                    f'style="background-color:transparent;border:0;text-align:center;width:50px;">',
                'Display_Name': fine_items[f'{param}{index}'].at["Display_Name"],
                '0': '-' if '_0' not in value.columns else
                f'<input type="text" class="table-value text-primary" id="{param}{index}-0" disabled value="{value.at[index, "_0"]}"'
                f'style="background-color:transparent;border:0;text-align:center;width:100px;">',
                '1': '-' if '_1' not in value.columns else
                f'<input type="text" class="table-value text-primary" id="{param}{index}-1" disabled value="{value.at[index, "_1"]}"'
                f'style="background-color:transparent;border:0;text-align:center;width:100px;">',
                '2': '-' if '_2' not in value.columns else
                f'<input type="text" class="table-value text-primary" id="{param}{index}-2" disabled value="{value.at[index, "_2"]}"'
                f'style="background-color:transparent;border:0;text-align:center;width:100px;">',
                '3': '-' if '_3' not in value.columns else
                f'<input type="text" class="table-value text-primary" id="{param}{index}-3" disabled value="{value.at[index, "_3"]}"'
                f'style="background-color:transparent;border:0;text-align:center;width:100px;">',
                '4': '-' if '_4' not in value.columns else
                f'<input type="text" class="table-value text-primary" id="{param}{index}-4" disabled value="{value.at[index, "_4"]}"'
                f'style="background-color:transparent;border:0;text-align:center;width:100px;">',
                '5': '-' if '_5' not in value.columns else
                f'<input type="text" class="table-value text-primary" id="{param}{index}-5" disabled value="{value.at[index, "_5"]}"'
                f'style="background-color:transparent;border:0;text-align:center;width:100px;">',
                '6': '-' if '_6' not in value.columns else
                f'<input type="text" class="table-value text-primary" id="{param}{index}-6" disabled value="{value.at[index, "_6"]}"'
                f'style="background-color:transparent;border:0;text-align:center;width:100px;">',
                '7': '-' if '_7' not in value.columns else
                f'<input type="text" class="table-value text-primary" id="{param}{index}-7" disabled value="{value.at[index, "_7"]}"'
                f'style="background-color:transparent;border:0;text-align:center;width:100px;">',
                '8': '-' if '_8' not in value.columns else
                f'<input type="text" class="table-value text-primary" id="{param}{index}-8" disabled value="{value.at[index, "_8"]}"'
                f'style="background-color:transparent;border:0;text-align:center;width:100px;">',
                '9': '-' if '_9' not in value.columns else
                f'<input type="text" class="table-value text-primary" id="{param}{index}-9" disabled value="{value.at[index, "_9"]}"'
                f'style="background-color:transparent;border:0;text-align:center;width:100px;">'
            })
    if 'F_' in param:
        for index in value.index:
            symbols_value['filters'].append({
                'Name': f'<span class="name text-theme" data-toggle="tooltip" data-placement="right" title="'
                f'{queried[param].at["Description_en_GB"] if param in queried.keys() else param}">{param}</span>',
                'Enabled':
                f'<input type="text" class="table-value enable-col text-danger" id="{param}{index}-Enabled" disabled value="{value.at[index, "Enabled"]}"'
                f'style="background-color:transparent;border:0;text-align:center;width:50px;">',
                'Display_Name': f'{index+1}',
                'Numerator_Type': value.at[index, "Numerator_Type"],
                'Denominator_Type': value.at[index, "Denominator_Type"],
                'Numerator_TC': value.at[index, "Numerator_TC"],
                'Denominator_TC': value.at[index, "Denominator_TC"],
                'Numerator_Frequency':
                f'<input type="text" class="table-value num-frequency-col text-primary" id="{param}{index}-Numerator_Frequency" disabled value="{value.at[index, "Numerator_Frequency"]}"'
                f'style="background-color:transparent;border:0;text-align:center;width:100px;" onkeyup="equals(\'{param}{index}-Numerator_Frequency\', \'{param}{index}-Denominator_Frequency\')">',
                'Numerator_Damping_Ratio':
                f'<input type="text" class="table-value text-primary" id="{param}{index}-Numerator_Damping_Ratio" disabled value="{value.at[index, "Numerator_Damping_Ratio"]}"'
                f'style="background-color:transparent;border:0;text-align:center;width:100px;">',
                'Denominator_Frequency':
                f'<input type="text" class="table-value den-frequency-col text-primary" id="{param}{index}-Denominator_Frequency" disabled value="{value.at[index, "Denominator_Frequency"]}"'
                f'style="background-color:transparent;border:0;text-align:center;width:100px;" onkeyup="equals(\'{param}{index}-Denominator_Frequency\', \'{param}{index}-Numerator_Frequency\')">',
                'Denominator_Damping_Ratio':
                f'<input type="text" class="table-value text-primary" id="{param}{index}-Denominator_Damping_Ratio" disabled value="{value.at[index, "Denominator_Damping_Ratio"]}"'
                f'style="background-color:transparent;border:0;text-align:center;width:100px;">',
                'W0':
                f'<input type="text" class="table-value text-primary" id="{param}{index}-W0" disabled value="{value.at[index, "W0"]}"'
                f'style="background-color:transparent;border:0;text-align:center;width:100px;">',
                'Prewarping_Wc':
                f'<input type="text" class="table-value text-primary" id="{param}{index}-Prewarping_Wc" disabled value="{value.at[index, "Prewarping_Wc"]}"'
                f'style="background-color:transparent;border:0;text-align:center;width:100px;">',
            })

    return jsonify(symbols_value)
