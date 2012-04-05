"""
sentry.web.frontend.projects
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

:copyright: (c) 2012 by the Sentry Team, see AUTHORS for more details.
:license: BSD, see LICENSE for more details.
"""
from django.core.context_processors import csrf
from django.core.urlresolvers import reverse
from django.http import HttpResponseRedirect
from django.views.decorators.csrf import csrf_protect

from sentry.conf import settings
from sentry.models import ProjectMember, MEMBER_OWNER, \
  ProjectKey
from sentry.permissions import can_create_projects, can_remove_project
from sentry.plugins import plugins
from sentry.web.decorators import login_required, has_access
from sentry.web.forms import EditProjectForm, NewProjectForm, \
  RemoveProjectForm, NewProjectAdminForm
from sentry.web.helpers import render_to_response, get_project_list, \
  plugin_config


@login_required
def project_list(request):
    project_list = get_project_list(request.user, hidden=True)
    memberships = list(ProjectMember.objects.filter(user=request.user, project__in=project_list))
    keys = dict((p.project_id, p) for p in ProjectKey.objects.filter(user=request.user, project__in=project_list))

    for member in memberships:
        project_id = member.project_id
        key = keys.get(project_id)
        if key:
            project_list[project_id].member_dsn = key.get_dsn()
        project_list[project_id].member_type = member.get_type_display()

    return render_to_response('sentry/projects/list.html', {
        'PROJECT_LIST': project_list.values(),
    }, request)


@login_required
@csrf_protect
def new_project(request):
    if not can_create_projects(request.user):
        return HttpResponseRedirect(reverse('sentry'))

    if request.user.has_perm('sentry.can_add_project'):
        form_cls = NewProjectAdminForm
        initial = {
            'owner': request.user.username,
        }
    else:
        form_cls = NewProjectForm
        initial = {}

    form = form_cls(request.POST or None, initial=initial)
    if form.is_valid():
        project = form.save(commit=False)
        if not project.owner:
            project.owner = request.user
        project.save()
        return HttpResponseRedirect(reverse('sentry-manage-project', args=[project.pk]))

    context = csrf(request)
    context.update({
        'form': form,
    })

    return render_to_response('sentry/projects/new.html', context, request)


@login_required
@has_access(MEMBER_OWNER)
@csrf_protect
def remove_project(request, project):
    if str(project.id) == str(settings.PROJECT):
        return HttpResponseRedirect(reverse('sentry-project-list'))

    if not can_remove_project(request.user, project):
        return HttpResponseRedirect(reverse('sentry'))

    project_list = filter(lambda x: x != project, get_project_list(request.user).itervalues())

    form = RemoveProjectForm(project_list, request.POST or None)

    if form.is_valid():
        removal_type = form.cleaned_data['removal_type']
        if removal_type == '1':
            project.delete()
        elif removal_type == '2':
            new_project = form.cleaned_data['project']
            project.merge_to(new_project)
        elif removal_type == '3':
            project.update(status=1)
        else:
            raise ValueError(removal_type)

        return HttpResponseRedirect(reverse('sentry-project-list'))

    context = csrf(request)
    context.update({
        'form': form,
        'project': project,
    })

    return render_to_response('sentry/projects/remove.html', context, request)


@login_required
@has_access(MEMBER_OWNER)
@csrf_protect
def manage_project(request, project):
    result = plugins.first('has_perm', request.user, 'edit_project', project)
    if result is False and not request.user.has_perm('sentry.can_change_project'):
        return HttpResponseRedirect(reverse('sentry'))

    form = EditProjectForm(request, request.POST or None, instance=project)

    if form.is_valid():
        project = form.save()

        return HttpResponseRedirect(request.path + '?success=1')

    member_list = [(tm, tm.user) for tm in project.team.member_set.select_related('user')]

    context = csrf(request)
    context.update({
        'can_remove_project': can_remove_project(request.user, project),
        'page': 'details',
        'form': form,
        'project': project,
        'member_list': member_list,
    })

    return render_to_response('sentry/projects/manage.html', context, request)


@login_required
@has_access(MEMBER_OWNER)
@csrf_protect
def configure_project_plugin(request, project, slug):
    try:
        plugin = plugins.get(slug)
    except KeyError:
        return HttpResponseRedirect(reverse('sentry-manage-project', args=[project.pk]))

    if not plugin.is_enabled(project):
        return HttpResponseRedirect(reverse('sentry-manage-project', args=[project.pk]))

    result = plugins.first('has_perm', request.user, 'configure_project_plugin', project, plugin)
    if result is False and not request.user.is_superuser:
        return HttpResponseRedirect(reverse('sentry'))

    form = plugin.project_conf_form
    if form is None:
        return HttpResponseRedirect(reverse('sentry-manage-project', args=[project.pk]))

    action, view = plugin_config(plugin, project, request)
    if action == 'redirect':
        return HttpResponseRedirect(request.path + '?success=1')

    context = csrf(request)
    context.update({
        'page': 'plugin',
        'title': plugin.get_title(),
        'view': view,
        'project': project,
        'plugin': plugin,
    })

    return render_to_response('sentry/projects/plugins/configure.html', context, request)


@login_required
@has_access(MEMBER_OWNER)
@csrf_protect
def manage_plugins(request, project):
    result = plugins.first('has_perm', request.user, 'configure_project_plugin', project)
    if result is False and not request.user.has_perm('sentry.can_change_project'):
        return HttpResponseRedirect(reverse('sentry'))

    if request.POST:
        enabled = set(request.POST.getlist('plugin'))
        for plugin in plugins.all():
            if plugin.can_enable_for_projects():
                plugin.set_option('enabled', plugin.slug in enabled, project)
        return HttpResponseRedirect(request.path + '?success=1')

    context = csrf(request)
    context.update({
        'page': 'plugins',
        'project': project,
    })

    return render_to_response('sentry/projects/plugins/list.html', context, request)
