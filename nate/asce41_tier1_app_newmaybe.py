import json, uuid
from datetime import datetime
import pandas as pd
import streamlit as st

st.set_page_config(page_title='MORGAN | ASCE 41 Tier 1 Navigator', page_icon='🏗️', layout='wide')

BUILDING_TYPES = {
    'S1': 'Steel moment frames with stiff diaphragms',
    'S1A': 'Steel moment frames with flexible diaphragms',
}
STATUS_LABELS = ['Not reviewed', 'Compliant', 'Noncompliant', 'Not applicable', 'Unknown']
COLS = ['id','checklist','building_types','performance','min_seismicity','diaphragm','section','topic','statement','tier2_ref','commentary_ref']
SEISMIC_RANK = {'Very Low': 0, 'Low': 1, 'Moderate': 2, 'High': 3}

def item(i, checklist, performance, minimum, diaphragm, section, topic, statement, tier2, commentary):
    return {'id': i, 'checklist': checklist, 'building_types': 'S1,S1A', 'performance': performance,
            'min_seismicity': minimum, 'diaphragm': diaphragm, 'section': section, 'topic': topic,
            'statement': statement, 'tier2_ref': tier2, 'commentary_ref': commentary}

CHECKLIST = [
# Table 17-8: Collapse Prevention
item('S1-CP-L-01','S1/S1A Collapse Prevention','CP','Low','Any','Seismic-Force-Resisting System','Redundancy','The number of lines of moment frames in each principal direction is greater than or equal to 2.','5.5.1.1','A.3.1.1.1'),
item('S1-CP-L-02','S1/S1A Collapse Prevention','CP','Low','Any','Seismic-Force-Resisting System','Drift Check','The drift ratio of the steel moment frames, calculated using the Quick Check procedure of Section 4.4.3.1, is less than 0.030.','5.5.2.1.2','A.3.1.3.1'),
item('S1-CP-L-03','S1/S1A Collapse Prevention','CP','Low','Any','Seismic-Force-Resisting System','Column Axial Stress Check','The axial stress caused by gravity loads in columns subjected to overturning forces is less than 0.10Fy. Alternatively, the axial stress caused by overturning forces alone, calculated using Section 4.4.3.6, is less than 0.30Fy.','5.5.2.1.3','A.3.1.3.2'),
item('S1-CP-L-04','S1/S1A Collapse Prevention','CP','Low','Any','Seismic-Force-Resisting System','Flexural Stress Check','The average flexural stress in the moment-frame columns and beams, calculated using Section 4.4.3.9, is less than Fy. Columns need not be checked if the strong column-weak beam item is compliant.','5.5.2.1.2','A.3.1.3.3'),
item('S1-CP-L-05','S1/S1A Collapse Prevention','CP','Low','Any','Connections','Transfer to Steel Frames','Diaphragms are connected for transfer of seismic forces to the steel frames.','5.7.2','A.5.2.2'),
item('S1-CP-L-06','S1/S1A Collapse Prevention','CP','Low','Any','Connections','Steel Columns','Columns in seismic-force-resisting frames are anchored to the building foundation.','5.7.3.1','A.5.3.1'),
item('S1-CP-M-01','S1/S1A Collapse Prevention','CP','Moderate','Any','Seismic-Force-Resisting System','Frame-Line Redundancy','The number of bays of moment frames in each line is greater than or equal to 2.','5.5.1.1','A.3.1.1.1'),
item('S1-CP-M-02','S1/S1A Collapse Prevention','CP','Moderate','Any','Seismic-Force-Resisting System','Interfering Walls','All concrete and masonry infill walls placed in moment frames are isolated from structural elements.','5.5.2.1.1','A.3.1.2.1'),
item('S1-CP-M-03','S1/S1A Collapse Prevention','CP','Moderate','Any','Seismic-Force-Resisting System','Moment-Resisting Connections','All moment connections can develop the strength of adjoining members based on the specified minimum yield stress of steel.','5.5.2.2.1','A.3.1.3.4'),
item('S1-CP-H-01','S1/S1A Collapse Prevention','CP','High','Any','Seismic-Force-Resisting System','Moment-Resisting Connections','All moment connections can develop the strength of adjoining members or panel zones based on 110% of expected yield stress in accordance with AISC 341, Section A3.2.','5.5.2.2.1','A.3.1.3.4'),
item('S1-CP-H-02','S1/S1A Collapse Prevention','CP','High','Any','Seismic-Force-Resisting System','Panel Zones','Panel zones have shear capacity for the demand required to develop 0.8 times the sum of girder flexural strengths framing in at the column face.','5.5.2.2.2','A.3.1.3.5'),
item('S1-CP-H-03','S1/S1A Collapse Prevention','CP','High','Any','Seismic-Force-Resisting System','Column Splices','Column splices in moment-resisting frames connect both flanges and the web.','5.5.2.2.3','A.3.1.3.6'),
item('S1-CP-H-04','S1/S1A Collapse Prevention','CP','High','Any','Seismic-Force-Resisting System','Strong Column-Weak Beam','More than 50% of joints in each story of each moment-frame line satisfy strong column-weak beam.','5.5.2.1.5','A.3.1.3.7'),
item('S1-CP-H-05','S1/S1A Collapse Prevention','CP','High','Any','Seismic-Force-Resisting System','Compact Members','Frame elements satisfy AISC 341 Table D1.1 requirements for moderately ductile members.','5.5.2.2.4','A.3.1.3.8'),
item('S1-CP-H-06','S1/S1A Collapse Prevention','CP','High','Any','Diaphragms','Openings at Frames','Diaphragm openings immediately adjacent to moment frames extend less than 25% of total frame length.','5.6.1.3','A.4.1.5'),
item('S1A-CP-H-01','S1/S1A Collapse Prevention','CP','High','Flexible','Flexible Diaphragms','Cross Ties','Continuous cross ties are present between diaphragm chords.','5.6.1.2','A.4.1.2'),
item('S1A-CP-H-02','S1/S1A Collapse Prevention','CP','High','Flexible','Flexible Diaphragms','Straight Sheathing','Straight-sheathed diaphragms have aspect ratios less than 2-to-1.','5.6.2','A.4.2.1'),
item('S1A-CP-H-03','S1/S1A Collapse Prevention','CP','High','Flexible','Flexible Diaphragms','Spans','Wood diaphragms spanning more than 24 ft consist of wood structural panels or diagonal sheathing.','5.6.2','A.4.2.2'),
item('S1A-CP-H-04','S1/S1A Collapse Prevention','CP','High','Flexible','Flexible Diaphragms','Diagonally Sheathed and Unblocked Diaphragms','Applicable diaphragms span less than 40 ft and have aspect ratios not exceeding 4-to-1.','5.6.2','A.4.2.3'),
item('S1A-CP-H-05','S1/S1A Collapse Prevention','CP','High','Flexible','Flexible Diaphragms','Other Diaphragms','Diaphragms are wood, metal deck, concrete, or horizontal bracing systems.','5.6.5','A.4.7.1'),
# Table 17-9: Immediate Occupancy
item('S1-IO-VL-01','S1/S1A Immediate Occupancy','IO','Very Low','Any','Seismic-Force-Resisting System','Drift Check','The steel moment-frame drift ratio calculated using Section 4.4.3.1 is less than 0.015.','5.5.2.1.2','A.3.1.3.1'),
item('S1-IO-VL-02','S1/S1A Immediate Occupancy','IO','Very Low','Any','Seismic-Force-Resisting System','Column Axial Stress Check','Gravity-load axial stress in columns subjected to overturning is less than 0.10Fy, or overturning-only axial stress from Section 4.4.3.6 is less than 0.30Fy.','5.5.2.1.3','A.3.1.3.2'),
item('S1-IO-VL-03','S1/S1A Immediate Occupancy','IO','Very Low','Any','Seismic-Force-Resisting System','Flexural Stress Check','Average flexural stress in moment-frame columns and beams from Section 4.4.3.9 is less than Fy; columns need not be checked when strong column-weak beam is compliant.','5.5.2.1.2','A.3.1.3.3'),
item('S1-IO-VL-04','S1/S1A Immediate Occupancy','IO','Very Low','Any','Connections','Steel Columns','Columns in seismic-force-resisting frames are anchored to the foundation.','5.7.3.1','A.5.3.1'),
item('S1-IO-L-01','S1/S1A Immediate Occupancy','IO','Low','Any','Seismic-Force-Resisting System','Redundancy','There are at least 2 moment-frame lines in each principal direction and at least 3 bays in each line.','5.5.1.1','A.3.1.1.1'),
item('S1-IO-L-02','S1/S1A Immediate Occupancy','IO','Low','Any','Seismic-Force-Resisting System','Interfering Walls','Concrete and masonry infill walls in moment frames are isolated from structural elements.','5.5.2.1.1','A.3.1.2.1'),
item('S1-IO-L-03','S1/S1A Immediate Occupancy','IO','Low','Any','Connections','Transfer to Steel Frames','Diaphragm connections can transfer seismic forces and develop the lesser of frame or diaphragm strength.','5.7.2','A.5.2.2'),
item('S1-IO-L-04','S1/S1A Immediate Occupancy','IO','Low','Any','Connections','Steel Columns','Column anchorage develops the least of column tensile capacity, lowest-level splice tensile capacity, or foundation uplift capacity.','5.7.3.1','A.5.3.1'),
item('S1-IO-M-01','S1/S1A Immediate Occupancy','IO','Moderate','Any','Seismic-Force-Resisting System','Moment-Resisting Connections','Moment connections develop expected strength of adjoining members based on specified minimum steel yield stress.','5.5.2.2.1','A.3.1.3.4'),
item('S1-IO-M-02','S1/S1A Immediate Occupancy','IO','Moderate','Any','Seismic-Force-Resisting System','Panel Zones','Panel zones resist demand required to develop 0.8 times the sum of girder flexural strengths at the column face.','5.5.2.2.2','A.3.1.3.5'),
item('S1-IO-M-03','S1/S1A Immediate Occupancy','IO','Moderate','Any','Seismic-Force-Resisting System','Column Splices','Moment-frame column splices connect both flanges and web and develop column strength.','5.5.2.2.3','A.3.1.3.6'),
item('S1-IO-M-04','S1/S1A Immediate Occupancy','IO','Moderate','Any','Seismic-Force-Resisting System','Strong Column-Weak Beam','More than 50% of joints in each story of each moment-frame line satisfy strong column-weak beam.','5.5.2.1.5','A.3.1.3.7'),
item('S1-IO-M-05','S1/S1A Immediate Occupancy','IO','Moderate','Any','Seismic-Force-Resisting System','Compact Members','Frame elements satisfy AISC 341 Table D1.1 requirements for highly ductile members.','5.5.2.2.4','A.3.1.3.8'),
item('S1-IO-M-06','S1/S1A Immediate Occupancy','IO','Moderate','Any','Seismic-Force-Resisting System','Beam Penetrations','Frame-beam web openings are less than one-quarter of beam depth and within the center half of beams.','5.5.2.2.5','A.3.1.3.9'),
item('S1-IO-M-07','S1/S1A Immediate Occupancy','IO','Moderate','Any','Seismic-Force-Resisting System','Girder Flange Continuity Plates','Girder flange continuity plates are present at all moment-frame joints.','5.5.2.2.6','A.3.1.3.10'),
item('S1-IO-M-08','S1/S1A Immediate Occupancy','IO','Moderate','Any','Seismic-Force-Resisting System','Out-of-Plane Bracing','Beam-column joints are braced out of plane.','5.5.2.2.7','A.3.1.3.11'),
item('S1-IO-M-09','S1/S1A Immediate Occupancy','IO','Moderate','Any','Seismic-Force-Resisting System','Bottom Flange Bracing','Beam bottom flanges are braced out of plane.','5.5.2.2.8','A.3.1.3.12'),
item('S1-IO-M-10','S1/S1A Immediate Occupancy','IO','Moderate','Any','Diaphragms','Plan Irregularities','Tensile capacity develops diaphragm strength at reentrant corners and other plan irregularities.','5.6.1.4','A.4.1.7'),
item('S1-IO-M-11','S1/S1A Immediate Occupancy','IO','Moderate','Any','Diaphragms','Reinforcement at Openings','Reinforcing is present around diaphragm openings larger than 50% of building width in either major plan dimension.','5.6.1.5','A.4.1.8'),
item('S1-IO-M-12','S1/S1A Immediate Occupancy','IO','Moderate','Any','Diaphragms','Openings at Frames','Openings immediately adjacent to moment frames extend less than 15% of total frame length.','5.6.1.3','A.4.1.5'),
item('S1A-IO-M-01','S1/S1A Immediate Occupancy','IO','Moderate','Flexible','Flexible Diaphragms','Cross Ties','Continuous cross ties are present between diaphragm chords.','5.6.1.2','A.4.1.2'),
item('S1A-IO-M-02','S1/S1A Immediate Occupancy','IO','Moderate','Flexible','Flexible Diaphragms','Straight Sheathing','Straight-sheathed diaphragms have aspect ratios less than 1-to-1.','5.6.2','A.4.2.1'),
item('S1A-IO-M-03','S1/S1A Immediate Occupancy','IO','Moderate','Flexible','Flexible Diaphragms','Spans','Wood diaphragms spanning more than 12 ft consist of wood structural panels or diagonal sheathing.','5.6.2','A.4.2.2'),
item('S1A-IO-M-04','S1/S1A Immediate Occupancy','IO','Moderate','Flexible','Flexible Diaphragms','Diagonally Sheathed and Unblocked Diaphragms','Applicable diaphragms span less than 30 ft and have aspect ratios not exceeding 3-to-1.','5.6.2','A.4.2.3'),
item('S1A-IO-M-05','S1/S1A Immediate Occupancy','IO','Moderate','Flexible','Flexible Diaphragms','Nonconcrete Filled Diaphragms','Untopped or nonconcrete-filled metal deck diaphragms span less than 40 ft and have aspect ratios less than 4-to-1.','5.6.3','A.4.3.1'),
item('S1A-IO-M-06','S1/S1A Immediate Occupancy','IO','Moderate','Flexible','Flexible Diaphragms','Other Diaphragms','Diaphragms are wood, metal deck, concrete, or horizontal bracing systems.','5.6.5','A.4.7.1'),
item('S1-IO-H-01','S1/S1A Immediate Occupancy','IO','High','Any','Seismic-Force-Resisting System','Moment-Resisting Connections','Moment connections develop adjoining-member or panel-zone strength based on 110% of expected yield stress in accordance with AISC 341 Section A3.2.','5.5.2.2.1','A.3.1.3.4'),
item('S1-IO-H-02','S1/S1A Immediate Occupancy','IO','High','Any','Foundation System','Deep Foundations','Piles and piers can transfer seismic forces between structure and soil.','','A.6.2.3'),
item('S1-IO-H-03','S1/S1A Immediate Occupancy','IO','High','Any','Foundation System','Sloping Sites','Foundation embedment depth differs by no more than one story from one side of the building to the other.','','A.6.2.4'),
]
DF = pd.DataFrame(CHECKLIST)[COLS]

st.session_state.setdefault('responses', {})
st.session_state.setdefault('project_id', str(uuid.uuid4())[:8])

st.title('MORGAN')
st.caption('Mapped Objective Review & Guided Assessment Navigator | ASCE 41 Tier 1')
st.warning('Engineering decision-support only. The design professional remains responsible for applicability, interpretation, calculations, and conclusions.')

with st.sidebar:
    st.header('Project setup')
    project = st.text_input('Project / building name')
    evaluator = st.text_input('Evaluator')
    objective = st.selectbox('Structural performance objective', ['Collapse Prevention (CP)', 'Immediate Occupancy (IO)'])
    perf = objective.split('(')[-1].rstrip(')')
    seismicity = st.selectbox('Seismicity', list(SEISMIC_RANK))
    btype = st.selectbox('Building type', list(BUILDING_TYPES), format_func=lambda x: f'{x} - {BUILDING_TYPES[x]}')

def applies(r):
    diaphragm_ok = r.diaphragm == 'Any' or (r.diaphragm == 'Flexible' and btype == 'S1A')
    return perf == r.performance and SEISMIC_RANK[seismicity] >= SEISMIC_RANK[r.min_seismicity] and diaphragm_ok

app = DF[DF.apply(applies, axis=1)].copy()
setup, review, findings, data = st.tabs(['1. Applicability', '2. Checklist', '3. Findings', '4. Data'])
with setup:
    c1,c2,c3,c4 = st.columns(4)
    c1.metric('Building type', btype); c2.metric('Objective', perf); c3.metric('Seismicity', seismicity); c4.metric('Statements', len(app))
    st.info('Seismicity requirements are cumulative. Flexible-diaphragm statements are shown only for S1A.')
with review:
    if app.empty:
        st.warning('No structural statements apply to this combination. For CP, Table 17-8 begins at Low Seismicity.')
    for section, rows in app.groupby('section', sort=False):
        st.subheader(section)
        for _, r in rows.iterrows():
            old = st.session_state.responses.get(r.id, {})
            with st.container(border=True):
                st.markdown(f'### {r.id} | {r.topic}')
                st.write(r.statement)
                status = st.radio('Status', STATUS_LABELS, index=STATUS_LABELS.index(old.get('status','Not reviewed')), horizontal=True, key='s_'+r.id)
                basis = st.text_area('Basis / observations / calculation reference', old.get('basis',''), key='b_'+r.id)
                action = st.text_area('Follow-up / Tier 2 action', old.get('action',''), key='a_'+r.id)
                st.caption(f'Tier 2: {r.tier2_ref or "not listed"} | Commentary: {r.commentary_ref}')
                st.session_state.responses[r.id] = {'status':status,'basis':basis,'action':action}
with findings:
    records=[]
    for _,r in app.iterrows():
        records.append({**r.to_dict(), **st.session_state.responses.get(r.id, {'status':'Not reviewed','basis':'','action':''})})
    out=pd.DataFrame(records)
    if not out.empty:
        st.dataframe(out[['id','section','topic','status','tier2_ref','action']], use_container_width=True, hide_index=True)
        st.download_button('Download findings CSV', out.to_csv(index=False).encode(), 'tier1_findings.csv', 'text/csv')
        meta={'project':project,'evaluator':evaluator,'objective':objective,'seismicity':seismicity,'building_type':btype,'project_id':st.session_state.project_id,'exported':datetime.now().isoformat()}
        st.download_button('Download project JSON', json.dumps({'metadata':meta,'responses':records},indent=2).encode(), 'tier1_project.json','application/json')
with data:
    st.dataframe(DF, use_container_width=True, hide_index=True)
    st.download_button('Download S1/S1A checklist CSV', DF.to_csv(index=False).encode(), 'asce41_s1_s1a_checklists.csv','text/csv')
