import io, json, os, uuid, zipfile
from datetime import datetime
import pandas as pd
import streamlit as st
import field_capture as fc
import site_visit as sv
import checklist_text

st.set_page_config(page_title='MORGAN | ASCE 41 Tier 1 Navigator', page_icon='🏗️', layout='wide')

BUILDING_TYPES = {
 'W1':'Wood light frames, one or more stories', 'W1A':'Wood light frames, multi-unit residential',
 'W2':'Wood frames, commercial/industrial', 'S1':'Steel moment frames', 'S2':'Steel braced frames',
 'S3':'Steel light frames', 'S4':'Steel frames with concrete shear walls', 'S5':'Steel frames with infill masonry shear walls',
 'CFS1':'Cold-formed steel bearing walls with flexible diaphragms', 'CFS2':'Cold-formed steel bearing walls with stiff diaphragms',
 'C1':'Concrete moment frames', 'C2':'Concrete shear walls with stiff diaphragms', 'C2A':'Concrete shear walls with flexible diaphragms',
 'C3':'Concrete frames with infill masonry shear walls', 'C3A':'Concrete frames with infill masonry shear walls and flexible diaphragms',
 'PC1':'Tilt-up/precast shear walls with flexible diaphragms', 'PC1A':'Tilt-up/precast shear walls with stiff diaphragms',
 'PC2':'Precast frames with shear walls', 'PC2A':'Precast frames without shear walls',
 'RM1':'Reinforced masonry bearing walls with flexible diaphragms', 'RM2':'Reinforced masonry bearing walls with stiff diaphragms',
 'URM':'Unreinforced masonry bearing walls', 'MH':'Manufactured housing'
}

STARTER = [
 {'id':'VL-01','checklist':'Very Low Seismicity','building_types':'ALL','performance':'CP,LS,IO','seismicity':'Very Low','section':'Structural Components','topic':'Load Path','statement':'Verify a complete, well-defined load path transfers inertial forces from all building mass to the foundation.','tier2_ref':'5.4.1.1','commentary_ref':'A.2.1.1'},
 {'id':'BC-01','checklist':'Basic Configuration','building_types':'ALL','performance':'CP,LS','seismicity':'Low,Moderate,High','section':'Building System - General','topic':'Load Path','statement':'Verify a complete and continuous load path, including elements and connections, to the foundation.','tier2_ref':'5.4.1.1','commentary_ref':'A.2.1.1'},
 {'id':'BC-02','checklist':'Basic Configuration','building_types':'ALL','performance':'CP,LS','seismicity':'Low,Moderate,High','section':'Building System - General','topic':'Adjacent Buildings','statement':'Evaluate whether separation from adjacent structures is adequate for the applicable performance objective.','tier2_ref':'5.4.1.2','commentary_ref':'A.2.1.2'},
 {'id':'BC-03','checklist':'Basic Configuration','building_types':'ALL','performance':'CP,LS','seismicity':'Low,Moderate,High','section':'Building System - General','topic':'Mezzanines','statement':'Verify interior mezzanine levels are independently braced or properly anchored to the lateral-force-resisting system.','tier2_ref':'5.4.1.3','commentary_ref':'A.2.1.3'},
]
COLS=['id','checklist','building_types','performance','seismicity','section','topic','statement','tier2_ref','commentary_ref']
STATUS_LABELS={'C':'Compliant','NC':'Noncompliant','N/A':'Not applicable','U':'Unknown'}

def init():
    st.session_state.setdefault('responses', {})
    if 'checklist' not in st.session_state:
        # The team's checklist file (src/ASCE 41.txt) when present, else the starter rows.
        path=os.environ.get('MORGAN_CHECKLIST_TXT') or checklist_text.DEFAULT_PATH
        rows=checklist_text.load_checklist(path)
        st.session_state.checklist=pd.DataFrame(rows or STARTER)[COLS]
        st.session_state.checklist_source=f'{os.path.basename(str(path))} ({len(rows)} items)' if rows else 'starter dataset'
    st.session_state.setdefault('project_id', str(uuid.uuid4())[:8])
    st.session_state.setdefault('photos', {})  # item id -> {name, takenAt, jpeg, location, note, interpretation}
    st.session_state.setdefault('visit', {'state':'open'})  # open -> reviewing -> closed
init()
visit=st.session_state.visit
locked=visit['state']=='closed'

# End of site visit: review what's left to check, then close the project and produce the report.
def end_visit(): st.session_state.visit={'state':'reviewing','review':None,'error':None}
def keep_open(): st.session_state.visit['state']='open'
def close_visit():
    v=st.session_state.visit
    rid=v['review']['createdAt']
    v['done']={i:bool(st.session_state.get(f'chk_{rid}_{i}')) for i in range(len(v['review']['checks']))}
    v['state']='closed'; v['closed_at']=datetime.now().isoformat(sep=' ',timespec='minutes')
def reopen(): st.session_state.visit['state']='open'

# Site photo + AI interpretation (field capture). Advisory only: the engineer applies a status explicitly.
def use_status(key, status): st.session_state['s_'+key]=STATUS_LABELS[status]
def add_to_basis(key, text):
    cur=st.session_state.get('b_'+key,'')
    st.session_state['b_'+key]=(cur+'\n\n' if cur else '')+text

def photo_panel(r):
    key=r.id
    saved=st.session_state.photos.get(key)
    if locked and not saved: return
    with st.expander('Site photo' + (' ✓' if saved else ''), expanded=False):
        src=None
        if not locked:
            # Camera only on request: collapsed expanders still render, and camera_input asks for permission on render.
            shot=st.camera_input('Take photo',key='cam_'+key) if st.toggle('Use camera',key='camon_'+key) else None
            picked=st.file_uploader('…or upload a photo',type=['jpg','jpeg','png','webp'],key='up_'+key)
            loc=st.text_input('Location in building (e.g. Level 2, grid C/4)',key='loc_'+key)
            note=st.text_input('Note for the interpretation (optional)',key='note_'+key)
            src=shot or picked
        if src and st.button('Interpret photo',key='go_'+key,type='primary'):
            try:
                jpeg=fc.prepare_photo(src.getvalue())
                ctx={'building_type':btype,'performance_level':perf,'seismicity':seismicity,'location_in_building':loc,'user_note':note,
                     'checklist_item':{'id':r.id,'title':r.topic,'text':r.statement}}
                # Keep the photo even if interpretation fails.
                saved=st.session_state.photos[key]={'name':f'{key}_{datetime.now():%Y%m%d-%H%M%S}.jpg','takenAt':datetime.now().isoformat(),
                                                   'jpeg':jpeg,'location':loc,'note':note,'interpretation':None}
                with st.spinner('Interpreting photo…'): saved['interpretation']=fc.interpret_photo(jpeg,ctx)
            except fc.InterpretError as e:
                st.error(f'Could not interpret photo ({e.code}): {e}')
        if not saved: return
        st.image(saved['jpeg'],caption=saved['name'],width='stretch')
        res=saved['interpretation']
        if not res: return
        st.markdown(f"**Summary:** {res['summary']}")
        if res['suggestedStatus']:
            label=STATUS_LABELS[res['suggestedStatus']]
            st.info(f"**Suggested status: {label}** (advisory)" + (f"\n\n{res['statusRationale']}" if res['statusRationale'] else ''))
            st.button(f'Use this status ({label})',key='use_'+key,on_click=use_status,args=(key,res['suggestedStatus']),disabled=locked)
        if res['observations']:
            st.markdown('**Observations**\n'+'\n'.join(f"- *{o.get('severity','info')}*: {o.get('description','')}" for o in res['observations']))
        if res['possibleDeficiencies']:
            st.markdown('**Possible deficiencies**\n'+'\n'.join(f"- {d.get('description','')} (confidence: {d.get('confidence','low')})" for d in res['possibleDeficiencies']))
        if res['followUp']:
            st.markdown('**Follow-up**\n'+'\n'.join(f'- {f}' for f in res['followUp']))
        if not res['imageQuality']['usable'] or res['imageQuality']['issues']:
            st.warning('Image quality: '+('; '.join(res['imageQuality']['issues']) or 'not usable'))
        field_note=f"Photo {saved['name']}: {res['summary']}"+''.join(f"\n- {o.get('description','')}" for o in res['observations'])
        st.button('Add interpretation to basis',key='addb_'+key,on_click=add_to_basis,args=(key,field_note),disabled=locked)
        st.caption(f"Interpreted by {res['model']} at {res['createdAt']}. The engineer makes every determination.")

st.title('MORGAN')
st.caption('Mapped Objective Review & Guided Assessment Navigator | ASCE 41 Tier 1 workflow prototype')
st.warning('Engineering decision-support only. The registered design professional remains responsible for applicability, interpretation, calculations, and conclusions. Checklist text in this prototype is a starter dataset and must be verified against the licensed standard.')

with st.sidebar:
    st.header('Project setup')
    project = st.text_input('Project / building name', disabled=locked)
    address = st.text_input('Location', disabled=locked)
    evaluator = st.text_input('Evaluator', disabled=locked)
    code_edition = st.selectbox('Standard edition', ['ASCE 41-17'], disabled=locked)
    objective = st.selectbox('Structural performance objective', ['Collapse Prevention (CP)','Life Safety (LS)','Immediate Occupancy (IO)'], disabled=locked)
    perf = objective.split('(')[-1].rstrip(')')
    seismicity = st.selectbox('Seismicity', ['Very Low','Low','Moderate','High'], disabled=locked)
    btype = st.selectbox('FEMA/ASCE common building type', list(BUILDING_TYPES), format_func=lambda x:f'{x} - {BUILDING_TYPES[x]}', disabled=locked)
    stories = st.number_input('Stories', 1, 200, 1, disabled=locked)
    area = st.number_input('Approx. floor area (ft²)', 0, step=1000, disabled=locked)
    st.divider()
    st.header('Site visit')
    if visit['state']=='open':
        st.button('End site visit', type='primary', on_click=end_visit, width='stretch',
                  help='Review what is still to check, then close the project and create the report.')
    else:
        st.caption('Reviewing before closing…' if visit['state']=='reviewing' else f"Closed {visit['closed_at']}.")
    st.divider()
    st.caption(f'Checklist: {st.session_state.checklist_source}')
    upload = st.file_uploader('Import verified checklist CSV', type='csv', disabled=locked)
    if upload:
        df=pd.read_csv(upload)
        missing=set(COLS)-set(df.columns)
        if missing: st.error('Missing columns: '+', '.join(sorted(missing)))
        else: st.session_state.checklist=df[COLS].fillna(''); st.session_state.checklist_source=f'{upload.name} ({len(df)} items)'; st.success(f'Loaded {len(df)} statements')
    if not os.environ.get('ANTHROPIC_API_KEY'):
        st.caption('AI photo interpretation and visit review are off: set ANTHROPIC_API_KEY before starting the app. Photos are still saved.')

# Applicability engine
df=st.session_state.checklist.copy()
def applies(r):
    types=[x.strip() for x in str(r.building_types).split(',')]
    perfs=[x.strip() for x in str(r.performance).split(',')]
    seism=[x.strip() for x in str(r.seismicity).split(',')]
    return ('ALL' in types or btype in types) and perf in perfs and seismicity in seism
app=df[df.apply(applies,axis=1)]

def collect_records():
    records=[]
    for _,r in app.iterrows():
        x=st.session_state.responses.get(r.id,{'status':'Not reviewed','basis':'','action':'','evidence':''})
        p=st.session_state.photos.get(r.id) or {}
        interp=p.get('interpretation') or {}
        records.append({**r.to_dict(),**x,'photo':p.get('name',''),'photo_suggested_status':interp.get('suggestedStatus') or '','photo_summary':interp.get('summary','')})
    return records
records=collect_records()
metadata={'project':project,'address':address,'evaluator':evaluator,'edition':code_edition,'objective':objective,'seismicity':seismicity,'building_type':btype,'stories':stories,'area_ft2':area,'project_id':st.session_state.project_id}

if visit['state']=='reviewing':
    if visit['review'] is None:
        with st.spinner('Reviewing the visit…'):
            try: visit['review']=sv.review_visit(metadata,records,st.session_state.photos)
            except fc.InterpretError as e:
                visit['review']=sv.fallback_review(records,st.session_state.photos); visit['error']=f'{e.code}: {e}'
    rv=visit['review']; rid=rv['createdAt']
    with st.container(border=True):
        st.subheader('End site visit')
        if visit['error']: st.warning(f"AI review unavailable ({visit['error']}). Showing checks from unresolved items and photo follow-ups.")
        if rv['summary']:
            st.markdown(rv['summary']); st.caption(f"AI-drafted by {rv['model']}. Advisory only.")
        if not rv['checks']: st.success('Nothing left to check.')
        for where,label in (('on_site','Before leaving site'),('office','Office follow-up')):
            group=[(i,c) for i,c in enumerate(rv['checks']) if c['where']==where]
            if not group: continue
            st.markdown(f'**{label}**')
            for i,c in group:
                st.checkbox(f"{c['priority'].upper()} · {c['itemId']+' · ' if c['itemId'] else ''}{c['title']}",key=f'chk_{rid}_{i}',help=c['reason'] or None)
        open_high=sum(1 for i,c in enumerate(rv['checks']) if c['where']=='on_site' and c['priority']=='high' and not st.session_state.get(f'chk_{rid}_{i}'))
        if open_high: st.warning(f'{open_high} high-priority on-site check(s) still open. You can still close; they will be listed as open in the report.')
        elif rv['model'] and rv['closeRationale']: st.info(rv['closeRationale'])
        c1,c2=st.columns(2)
        c1.button('Keep visit open',on_click=keep_open,width='stretch')
        c2.button('Confirm and close project',type='primary',on_click=close_visit,width='stretch')
elif visit['state']=='closed':
    report=sv.build_report_html(metadata,records,st.session_state.photos,visit['review'],visit['done'],visit['closed_at'])
    with st.container(border=True):
        st.success(f"Site visit closed {visit['closed_at']}. The project is read-only.")
        c1,c2=st.columns(2)
        c1.download_button('Download site visit report (HTML)',report.encode(),f'site_visit_report_{st.session_state.project_id}.html','text/html',type='primary',width='stretch')
        c2.button('Reopen project',on_click=reopen,width='stretch')

setup, review, summary, data = st.tabs(['1. Applicability','2. Checklist','3. Findings','4. Data'])
with setup:
    st.subheader('Applicability summary')
    c1,c2,c3,c4=st.columns(4)
    c1.metric('Building type',btype); c2.metric('Objective',perf); c3.metric('Seismicity',seismicity); c4.metric('Statements',len(app))
    st.info('Recommended production logic: general checklist → performance-specific basic configuration → building-type structural checklist → nonstructural checklist, filtered by seismicity and objective.')
    st.markdown('**Gating questions to add before production use**')
    st.checkbox('Building type has been confirmed from drawings and field observations')
    st.checkbox('Seismicity and performance objective have been established under ASCE 41')
    st.checkbox('Site visit / condition assessment information is available')
    st.checkbox('Required quick-check parameters and material properties are available')

with review:
    if app.empty: st.warning('No statements match. Import a verified checklist CSV or adjust applicability inputs.')
    sections=list(dict.fromkeys(app.section.tolist()))
    sec=st.selectbox('Section',sections) if sections else None
    rows=app[app.section==sec] if sec else app
    done=0
    for _,r in rows.iterrows():
        key=r.id
        old=st.session_state.responses.get(key,{})
        with st.container(border=True):
            st.markdown(f'### {r.id} | {r.topic}')
            st.write(r.statement)
            a,b=st.columns([3,1])
            with a:
                status=st.radio('Status',['Not reviewed','Compliant','Noncompliant','Not applicable','Unknown'],index=['Not reviewed','Compliant','Noncompliant','Not applicable','Unknown'].index(old.get('status','Not reviewed')),horizontal=True,key='s_'+key,disabled=locked)
                basis=st.text_area('Basis / observations / calculation reference',old.get('basis',''),key='b_'+key,disabled=locked)
                action=st.text_area('Follow-up / Tier 2 action',old.get('action',''),key='a_'+key,disabled=locked)
            with b:
                st.markdown(f'**Tier 2:** {r.tier2_ref}')
                st.markdown(f'**Commentary:** {r.commentary_ref}')
                evidence=st.text_input('Evidence link / filename',old.get('evidence',''),key='e_'+key,disabled=locked)
            photo_panel(r)
            st.session_state.responses[key]={'status':status,'basis':basis,'action':action,'evidence':evidence}
            done += status!='Not reviewed'
    st.progress(done/max(len(rows),1),text=f'{done} of {len(rows)} reviewed in this section')

with summary:
    records=collect_records()  # again, to include edits made in the Checklist tab on this run
    out=pd.DataFrame(records)
    counts=out.status.value_counts() if not out.empty else pd.Series(dtype=int)
    cols=st.columns(5)
    for col,label in zip(cols,['Compliant','Noncompliant','Not applicable','Unknown','Not reviewed']): col.metric(label,int(counts.get(label,0)))
    if not out.empty:
        st.subheader('Items requiring resolution')
        st.dataframe(out[out.status.isin(['Noncompliant','Unknown','Not reviewed'])][['id','section','topic','status','tier2_ref','action']],use_container_width=True,hide_index=True)
        st.download_button('Download findings CSV',out.to_csv(index=False).encode(),'tier1_findings.csv','text/csv')
        photos={k:{f:v for f,v in p.items() if f!='jpeg'} for k,p in st.session_state.photos.items()}
        st.download_button('Download project JSON',json.dumps({'metadata':{**metadata,'exported':datetime.now().isoformat()},'responses':records,'photos':photos,'visit':visit},indent=2).encode(),'tier1_project.json','application/json')
        if st.session_state.photos:
            buf=io.BytesIO()
            with zipfile.ZipFile(buf,'w') as z:
                for p in st.session_state.photos.values(): z.writestr(p['name'],p['jpeg'])
            st.download_button('Download site photos (ZIP)',buf.getvalue(),'tier1_photos.zip','application/zip')

with data:
    st.subheader('Checklist data model')
    st.dataframe(df,use_container_width=True,hide_index=True)
    template=pd.DataFrame(columns=COLS)
    st.download_button('Download blank checklist template',template.to_csv(index=False).encode(),'asce41_checklist_template.csv','text/csv')
    st.caption('Use one row per evaluation statement. Separate multiple building types, performance levels, or seismicity levels with commas; use ALL when universal.')
