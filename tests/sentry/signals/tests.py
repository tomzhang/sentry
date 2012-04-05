# -*- coding: utf-8 -*-

from __future__ import absolute_import

from django.contrib.auth.models import User
from sentry.models import Project, Team, MEMBER_OWNER

from tests.base import TestCase


class SentrySignalTest(TestCase):
    def test_create_team_for_project(self):
        user = User.objects.create(username='foo')
        project = Project.objects.create(name='foo', owner=user, slug='foo')
        self.assertNotEquals(project.team, None)

    def test_create_team_member_for_owner(self):
        user = User.objects.create(username='foo')
        team = Team.objects.create(name='foo', slug='foo', owner=user)
        self.assertTrue(team.member_set.filter(user=user, type=MEMBER_OWNER).exists())
