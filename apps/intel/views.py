from django.http import HttpResponse, HttpResponseRedirect, Http404, HttpRequest
from django.template import RequestContext
from django.core.exceptions import *

from rapidsms.webui.utils import render_to_response

from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import redirect_to_login
from django.utils.translation import ugettext_lazy as _
from django.db.models.query_utils import Q
from xformmanager.models import *
from graphing import dbhelper
from django.utils.encoding import *
from hq.models import *

import hq.utils as utils
from domain.decorators import login_and_domain_required

from transformers.csv import UnicodeWriter
from StringIO import StringIO

from datetime import timedelta
from django.db import transaction
import uuid

from graphing.models import *
import logging
import hashlib
import settings
import traceback
import sys
import os
import string

import reports.util as util
from reports.custom.all.shared import get_data_by_chw, get_case_info
from reports.models import Case, SqlReport

import intel.queries as queries

@login_and_domain_required
def homepage(request):
    '''Splash page'''
    return render_to_response(request, "home.html")
    

######## Report Methods
@login_and_domain_required
def all_mothers_report(request):
    '''View all mothers - default'''
    return custom_report(request, 3, "chw_submission_details", "all")

@login_and_domain_required
def hi_risk_report(request):
    '''View only hi risk'''
    return custom_report(request, 3, "hi_risk_pregnancies", "risk")

@login_and_domain_required
def mother_details(request):
    '''view details for a mother'''
    return custom_report(request, 3, "_mother_summary", "single")
    


def custom_report(request, domain_id, report_name, page):
    context = {}
    context['page'] = page
    context["report_name"] = report_name
    report_method = util.get_report_method(request.user.selected_domain, report_name)
    # return HttpResponse(report_method(request))
    if not report_method:
        return render_to_response(request, 
                                  "report_not_found.html",
                                  context)
    context["report_display"] = report_method.__doc__
    context["report_body"] = report_method(request)
    
    if 'search' not in request.GET.keys(): 
        context['search_term'] = ''
    else:
        context['search_term'] = request.GET['search']
    
    context['print_view'] = (page != "single")
        
    if request.GET.has_key('print'):
        context['printmode'] = True
        template = "report_print.html"
    else:
        template = "report_base.html"
        
    return render_to_response(request, template, context)


######## Chart Methods

@login_and_domain_required
def chart(request):
    return view_graph(request, 20)

def clinic_chart(request):
    return view_clinic_graph(request, 27)
    
'''
select  DATE_FORMAT(timeend,'%m/%d/%Y'), username, count(*)
from xformmanager_metadata meta,
xformmanager_formdefmodel forms, hq_domain domains
where username <> 'admin' and forms.id = meta.formdefmodel_id
and forms.domain_id = domains.id
and domains.name = 'Grameen'
and meta.timeend > '2009-03-23'
and meta.timeend < '2010-03-24'
group by
DATE_FORMAT(timeend,'%m/%d/%Y'), username
order by timeend asc;
'''

def view_graph(request, graph_id, template_name="chart.html"):
    context = {}    
    graph = RawGraph.objects.all().get(id=graph_id)

    graph.domain = request.user.selected_domain.name
    startdate, enddate = utils.get_dates(request, 365) #graph.default_interval)
    graph.startdate = startdate.strftime("%Y-%m-%d")
    graph.enddate = (enddate + timedelta(days=1)).strftime("%Y-%m-%d")

    context['chart_title'] = graph.title
    
    context['chart_data'] = graph.get_flot_data()
    context['thegraph'] = graph
    
    context['page'] = "chart"

    rootgroup = utils.get_chart_group(request.user)    
    graphtree = get_graphgroup_children(rootgroup)    
    context['graphtree'] = graphtree
    context['view_name'] = 'chart.html'
    context['width'] = graph.width
    context['height'] = graph.height
    context['empty_dict'] = {}
    context['datatable'] = graph.convert_data_to_table(context['chart_data'])
        
    context['total_hi_risk'] = len(queries.hi_risk())
    context['total_registrations'] = len(queries.registrations())
    context['total_follow_up'] = len(queries.follow_up())
        
    # get per CHW table for show/hide
    report = SqlReport.objects.get(id=1)
    report_table = report.to_html_table() # {"whereclause": whereclause})    
    
    context['report_table'] = report_table
    
    for item in request.GET.items():
        if item[0] == 'bare':
            template_name = 'graphing/view_graph_bare.html'
        elif item[0] == 'data':
            template_name='graphing/view_graph_data.html'
        elif item[0] == 'csv':             
            return _get_chart_csv(graph)
            
    return render_to_response(request, template_name, context)
    
def get_graphgroup_children(graph_group):
    ret = {}
    children = GraphGroup.objects.all().filter(parent_group=graph_group)
    for child in children:
        ret[child] = get_graphgroup_children(child)
    return ret
    
    
# per clinic UI

def view_clinic_graph(request, graph_id, template_name="clinic_chart.html"):
    
    context = {}
    graph = RawGraph.objects.all().get(id=graph_id)

    graph.domain = request.user.selected_domain.name
    startdate, enddate = utils.get_dates(request, 365) 
    graph.startdate = startdate.strftime("%Y-%m-%d")
    graph.enddate = (enddate + timedelta(days=1)).strftime("%Y-%m-%d")

    context['chart_title'] = graph.title
    
    context['chart_data'] = graph.get_flot_data()
    context['thegraph'] = graph
    
    context['page'] = "chart"

    rootgroup = utils.get_chart_group(request.user)    
    graphtree = get_graphgroup_children(rootgroup)    
    context['graphtree'] = graphtree
    context['view_name'] = 'chart.html'
    context['width'] = graph.width
    context['height'] = graph.height
    context['empty_dict'] = {}
    context['datatable'] = graph.convert_data_to_table(context['chart_data'])
    

    clinics = queries.clinics()
    d = {
        'reg' : queries.registrations_by_clinic(),
        'hi_risk' : queries.hi_risk_by_clinic(),
        'follow' : queries.followup_by_clinic()
        }

    context['clinics'] = []    
    for c in clinics:
        for k in d.keys():
            if not d[k].has_key(c):
                d[k][c] = 0
        context['clinics'].append({'name': c, 'reg': d['reg'][c], 'hi_risk': d['hi_risk'][c], 'follow': d['follow'][c]})
    
    # context['total_hi_risk'] = len(queries.hi_risk())
    # context['total_registrations'] = len(queries.registrations())
    # context['total_follow_up'] = len(queries.follow_up())
    

    # get per CHW table for show/hide
    report = SqlReport.objects.get(id=1)
    report_table = report.to_html_table() # {"whereclause": whereclause})    

    # import pprint ; pprint.pprint(context['totals'])

    print context['clinics']
    
    context['report_table'] = report_table
    
    for item in request.GET.items():
        if item[0] == 'bare':
            template_name = 'graphing/view_graph_bare.html'
        elif item[0] == 'data':
            template_name='graphing/view_graph_data.html'
        elif item[0] == 'csv':             
            return _get_chart_csv(graph)
            
    return render_to_response(request, template_name, context)