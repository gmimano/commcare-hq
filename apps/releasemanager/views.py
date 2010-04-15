import datetime
import logging
import os
import shutil
import time

from django.contrib.auth.models import User
from hq.utils import build_url
from domain.models import Domain
from domain.decorators import login_and_domain_required
from requestlogger.models import RequestLog
from xformmanager.manager import readable_form, csv_dump

import releasemanager.lib as lib

# from buildmanager.exceptions import BuildError
# from buildmanager.models import *
# from buildmanager.forms import *
# from buildmanager.jar import validate_jar
# from buildmanager import xformvalidator

from releasemanager.forms import *

from rapidsms.webui.utils import render_to_response

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseRedirect
from django.contrib.auth.models import User
from django.http import *
from django.http import HttpResponse
from django.http import HttpResponseRedirect, Http404
from django.core.urlresolvers import reverse

import mimetypes
import urllib

FILE_PATH = settings.RAPIDSMS_APPS['releasemanager']['file_path']

@login_and_domain_required
def jarjad_set_release(request, id, set_to):
    if set_to == "true" or set_to == "false":
        Jarjad.objects.filter(id=id).update(is_release=(set_to == "true"))
    return HttpResponseRedirect(reverse('releasemanager.views.jarjad'))
    
@login_and_domain_required
def jarjad(request, template_name="jarjad.html"): 
    context = {'form' : JarjadForm(), 'items': {}}
    context['items']['unreleased'] = Jarjad.objects.filter(is_release=False).order_by('-created_at')
    context['items']['released']   = Jarjad.objects.filter(is_release=True).order_by('-created_at')
    
    return render_to_response(request, template_name, context)


@login_and_domain_required
def make_release(request, id):
    Jarjad.objects.all().update(is_release=False)
    Jarjad.objects.filter(id=id).update(is_release=True)
    return HttpResponseRedirect(reverse('releasemanager.views.jarjad'))
    

@login_and_domain_required
def new_jarjad(request, template_name="jarjad.html"):
    '''save new Jad & Jar into the system'''
    xml_mode = ('CCHQ-submitfromfile' in request.META['HTTP_USER_AGENT'])
        
    context = {}
    form = JarjadForm()    
    if request.method == 'POST':
        form = JarjadForm(request.POST, request.FILES)                
        if form.is_valid():
            # try:                      
            jj = form.save(commit=False)
            jj.uploaded_by=request.user
            jj.description = urllib.unquote(jj.description)
                    
            jj.save_file(request.FILES['jad_file_upload'])
            jj.save_file(request.FILES['jar_file_upload'])
                    
            jj.save()
            
            # _log_build_upload(request, newbuild)
            return HttpResponse("SUCCESS") if xml_mode else HttpResponseRedirect(reverse('releasemanager.views.jarjad'))
            # except Exception, e:
            #     logging.error("Build upload error.", 
            #                   extra={'exception':e, 
            #                          'request.POST': request.POST, 
            #                          'request.FILES': request.FILES, 
            #                          'form':form})
            #     context['errors'] = "Could not commit: " + str(e)
    
    context['form'] = form
    return HttpResponse(form.errors) if xml_mode else render_to_response(request, template_name, context)
    
    

@login_and_domain_required
def builds(request, template_name="builds.html"): 
    context = {'form' : BuildForm(), 'items': {}}
    context['items']['unreleased'] = Build.objects.filter(is_release=False).order_by('-created_at')
    context['items']['released']   = Build.objects.filter(is_release=True).order_by('-created_at')

    return render_to_response(request, template_name, context)


@login_and_domain_required
def build_set_release(request, id, set_to):
    if set_to == "true" or set_to == "false":
        Build.objects.filter(id=id).update(is_release=(set_to == "true"))
    return HttpResponseRedirect(reverse('releasemanager.views.builds'))


@login_and_domain_required
def new_build(request, template_name="builds.html"):
    context = {}
    form = BuildForm()    
    if request.method == 'POST':
        form = BuildForm(request.POST)
        if form.is_valid():
            # try:                      
            b = form.save(commit=False)

            b.jar_file, b.jad_file, b.zip_file = _create_build(b)
        
            b.save()
            return HttpResponseRedirect(reverse('releasemanager.views.builds'))
            # except Exception, e:
            #     logging.error("Build upload error.", 
            #                   extra={'exception':e, 
            #                          'request.POST': request.POST, 
            #                          'form':form})
            #     context['errors'] = "Could not commit: " + str(e)

    context['form'] = form
    return render_to_response(request, template_name, context)

def _create_build(build):
    jar = build.jarjad.jar_file
    jad = build.jarjad.jad_file
    buildname = build.resource_set.name

    resource_zip = lib.grab_from(build.resource_set.url)
    resources = lib.unzip_to_tmp(resource_zip)

    ids = Build.objects.order_by('-id').filter(resource_set=build.resource_set)
    new_id = (1 + ids[0].id) if len(ids) > 0 else 1
    # new_id = str(1 + Build.objects.order_by('-id').filter(resource_set=build.resource_set)[0].id)
    
    new_path = os.path.join(BUILD_PATH, build.resource_set.domain.name, buildname, str(new_id))
    if not os.path.isdir(new_path):
        os.makedirs(new_path)


    # str() to converts the names to ascii from unicode - zip has problems with unicode filenames

    new_tmp_jar = lib.add_to_jar(jar, resources)    
    new_jar = str(os.path.join(new_path, "%s.jar" % buildname))
    shutil.copy2(new_tmp_jar, new_jar)

    new_tmp_jad = lib.modify_jad(jad, new_jar)
    new_jad = str(os.path.join(new_path, "%s.jad" % buildname))
    shutil.copy2(new_tmp_jad, new_jad)
        
    
    # create a zip
    new_zip = lib.create_zip(os.path.join(new_path, "%s.zip" % buildname), [new_jar, new_jad])
    
    # # clean up tmp files
    os.remove(new_tmp_jar)
    os.remove(new_tmp_jad)
            
    return new_jar, new_jad, new_zip


@login_and_domain_required
def resource_sets(request, template_name="resource_sets.html"): 
    context = {'form' : ResourceSetForm(), 'items': {}}
    context['items']['unreleased'] = ResourceSet.objects.filter(is_release=False).order_by('-created_at')
    context['items']['released']   = ResourceSet.objects.filter(is_release=True).order_by('-created_at')

    return render_to_response(request, template_name, context)


@login_and_domain_required
def resource_set_set_release(request, id, set_to):
    if set_to == "true" or set_to == "false":
        ResourceSet.objects.filter(id=id).update(is_release=(set_to == "true"))
    return HttpResponseRedirect(reverse('releasemanager.views.resource_sets'))


@login_and_domain_required
def new_resource_set(request, template_name="resource_sets.html"):
    context = {}
    form = ResourceSetForm()    
    if request.method == 'POST':
        form = ResourceSetForm(request.POST)
        if form.is_valid():
            try:                      
                b = form.save(commit=False)
                b.domain = request.user.selected_domain
                b.save()
                return HttpResponseRedirect(reverse('releasemanager.views.resource_sets'))
            except Exception, e:
                logging.error("Build upload error.", 
                              extra={'exception':e, 
                                     'request.POST': request.POST, 
                                     'form':form})
                context['errors'] = "Could not commit: " + str(e)

    context['form'] = form
    return render_to_response(request, template_name, context)