import os

from django.test import TestCase

from xformmanager.models import FormDefModel
from buildmanager.tests.util import setup_build_objects, create_build
from buildmanager.models import Project, ProjectBuild, BuildDownload, BuildForm

class ReleaseTestCase(TestCase):

    def setUp(self):
        user, domain, project, build = setup_build_objects(jar_file_name="Test.jar")
        self.domain = domain
        self.user = user
        self.project = project
        self.build = build

    def testRelease(self):
        self.assertEqual(0, len(FormDefModel.objects.all()))
        # the saving of the build should have auto-created these
        try:
            self.build.release(self.user)
            self.fail("Releasing a released build should fail!")
        except Exception:
            pass
        self.build.status = "build"
        self.build.save()
        self.build.release(self.user)
        formdefs = FormDefModel.objects.all()
        self.assertEqual(2, len(formdefs), "Releasing a build did not register xforms!")
        
        # try to reset it and release again
        self.build.status = "build"
        self.build.save()
        self.build.release(self.user)
        formdefs = FormDefModel.objects.all()
        self.assertEqual(2, len(formdefs), "Releasing a build twice registered extra xforms!")
        
        bad_jars = ["ExtraMetaField.jar","DuplicateMetaField.jar","MissingMetaField.jar",
                    "NoXmlns.jar"]
        build_number = 2
        for bad_jar in bad_jars:
            bad_build = create_build(self.user, self.domain, self.project, status="build",
                                     jar_file_name=bad_jar, build_number=build_number)
            build_number += 1
            try:
                bad_build.release()
                self.fail("Releasing a bad build: %s should fail!" % bad_jar)
            except Exception:
                pass
        