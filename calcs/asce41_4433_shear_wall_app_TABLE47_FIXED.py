import json
import pandas as pd
import streamlit as st

st.set_page_config(page_title='ASCE 41-17 4.4.3.3 Quick Check', page_icon='🏗️', layout='wide')
st.title('ASCE 41-17 §4.4.3.3 | Shear Stress in Shear Walls')
st.caption('Guided Tier 1 Quick Check including calculation of Vj')
st.warning('Engineering calculation aid. Verify inputs, applicability, and conclusions against the licensed standard.')

# Table 4-7 values transcribed from the user-provided table.
C_TABLE = {
    'Wood and cold-formed steel shear wall (W1, W1a, W2, CFS1)': [1.3, 1.1, 1.0, 1.0],
    'Moment frame (S1, S3, C1, PC2a)': [1.3, 1.1, 1.0, 1.0],
    'Shear wall (S4, S5, C2, C3, PC1a, PC2, RM2, URMa)': [1.4, 1.2, 1.1, 1.0],
    'Braced frame (S2)': [1.4, 1.2, 1.1, 1.0],
    'Cold-formed steel strap-braced wall (CFS2)': [1.4, 1.2, 1.1, 1.0],
    'Unreinforced masonry (URM)': [1.0, 1.0, 1.0, 1.0],
    'Flexible diaphragms (S1a, S2a, S5a, C2a, C3a, PC1, RM1)': [1.0, 1.0, 1.0, 1.0],
}
STORY_LABELS=['1','2','3','4 or more']
STORY_INDEX={x:i for i,x in enumerate(STORY_LABELS)}

st.header('1. Analysis point')
a,b=st.columns(2)
with a: direction=st.selectbox('Direction of loading',['X','Y'])
with b: units=st.selectbox('Wall stress units',['ksi','ksf'])

st.header('2. Calculate story shear Vj')
st.subheader('2A. Determine modification factor C from Table 4-7')
a,b=st.columns(2)
with a:
    building_type=st.selectbox('Building type / system',list(C_TABLE.keys()))
with b:
    story_band=st.selectbox('Number of stories',STORY_LABELS)
C=C_TABLE[building_type][STORY_INDEX[story_band]]
st.success(f'Table 4-7 gives **C = {C:.2f}** for **{building_type}** with **{story_band} stor{"y" if story_band=="1" else "ies"}**.')
st.metric('Modification factor, C',f'{C:.2f}')

st.subheader('2B. Pseudo seismic force V')
st.latex(r'V = C S_a W')
a,b=st.columns(2)
with a:
    Sa=st.number_input('Spectral acceleration Sa (g)',min_value=0.0,value=0.0,step=0.05,format='%.4f')
with b:
    W=st.number_input('Total seismic weight W (kips)',min_value=0.0,value=0.0,step=100.0,format='%.3f')
V=C*Sa*W
st.info(f'Using C = {C:.2f}:  V = ({C:.2f})({Sa:.4f})({W:.3f}) = **{V:,.3f} kips**')

st.subheader('2C. Vertical distribution exponent k')
T=st.number_input('Fundamental period T (sec)',min_value=0.0,value=0.5,step=0.05,format='%.3f')
use_six=st.checkbox('Building is 6 stories or fewer: use permitted k = 1.0 simplification',value=False)
if use_six:
    k=1.0
elif T<=0.5:
    k=1.0
elif T>2.5:
    k=2.0
else:
    k=1.0+(T-0.5)/2.0
st.metric('Vertical distribution exponent, k',f'{k:.3f}')

st.subheader('2D. Distribute V vertically')
st.latex(r'F_x = \frac{w_x h_x^k}{\sum_{i=1}^{n} w_i h_i^k}V')
st.write('Enter one row for each level. Height is measured from the base.')
if 'levels' not in st.session_state:
    st.session_state.levels=pd.DataFrame([
        {'Level':1,'Weight wi (kips)':0.0,'Height hi (ft)':0.0},
        {'Level':2,'Weight wi (kips)':0.0,'Height hi (ft)':0.0},
    ])
levels=st.data_editor(st.session_state.levels,num_rows='dynamic',use_container_width=True,key='levels_editor',
    column_config={
      'Level':st.column_config.NumberColumn('Level',min_value=1,step=1),
      'Weight wi (kips)':st.column_config.NumberColumn('Weight wi (kips)',min_value=0.0,format='%.3f'),
      'Height hi (ft)':st.column_config.NumberColumn('Height hi (ft)',min_value=0.0,format='%.3f')})
st.session_state.levels=levels
calc=levels.copy()
for col in ['Level','Weight wi (kips)','Height hi (ft)']:
    calc[col]=pd.to_numeric(calc[col],errors='coerce').fillna(0)
calc['wi hi^k']=calc['Weight wi (kips)']*calc['Height hi (ft)']**k
den=calc['wi hi^k'].sum()
calc['Fx (kips)']=calc['wi hi^k']/den*V if den>0 else 0.0
calc=calc.sort_values('Level')
st.dataframe(calc,use_container_width=True,hide_index=True)

st.subheader('2E. Calculate Vj')
st.latex(r'V_j = \sum_{x=j}^{n}F_x')
valid=sorted(calc.loc[calc['Level']>0,'Level'].astype(int).unique().tolist())
if valid:
    j=st.selectbox('Story level j',valid)
    Vj=float(calc.loc[calc['Level']>=j,'Fx (kips)'].sum())
else:
    j=1; Vj=0.0
st.metric(f'Story shear Vj at Level {j}',f'{Vj:,.3f} kips')

st.header('3. Determine Ms')
wall_class=st.selectbox('Wall category for Table 4-8',[
    'Reinforced concrete / precast concrete / wood / reinforced masonry / cold-formed steel',
    'Unreinforced masonry'])
perf=st.selectbox('Performance level',['Collapse Prevention (CP)','Life Safety (LS)','Immediate Occupancy (IO)'])
MS={
 'Reinforced concrete / precast concrete / wood / reinforced masonry / cold-formed steel':{'Collapse Prevention (CP)':4.5,'Life Safety (LS)':3.0,'Immediate Occupancy (IO)':1.5},
 'Unreinforced masonry':{'Collapse Prevention (CP)':1.75,'Life Safety (LS)':1.25,'Immediate Occupancy (IO)':1.0}}
Ms=MS[wall_class][perf]
st.info(f'Table 4-8 gives **Ms = {Ms:g}** for {wall_class}, {perf}.')

st.header('4. Effective shear-wall measure Aw')
material=st.selectbox('Wall area treatment',['Concrete / reinforced masonry / cold-formed steel','Unreinforced masonry','Wood-framed walls'])
st.write('Enter the participating walls in the selected direction. Use net dimensions accounting for openings as applicable.')
if 'walls' not in st.session_state:
    st.session_state.walls=pd.DataFrame([{'Wall':'W1','Net length (ft)':0.0,'Thickness (in)':0.0}])
walls=st.data_editor(st.session_state.walls,num_rows='dynamic',use_container_width=True,key='walls_editor')
st.session_state.walls=walls
L=pd.to_numeric(walls['Net length (ft)'],errors='coerce').fillna(0)
t=pd.to_numeric(walls['Thickness (in)'],errors='coerce').fillna(0)

if material=='Wood-framed walls':
    measure=float(L.sum())
    if units=='ksi': measure*=12
    Aw_text=f'{L.sum():.3f} ft of wall length'
    result_units='kips/in' if units=='ksi' else 'kips/ft'
else:
    area_in2=float((L*12*t).sum())
    measure=area_in2 if units=='ksi' else area_in2/144
    Aw_text=f'{area_in2:.3f} in²'
    result_units=units
st.metric('Aw used in Eq. 4-8',Aw_text)

st.header('5. Section 4.4.3.3 result')
st.latex(r'v_j^{avg}=\frac{V_j}{M_s A_w}')
if measure>0:
    vavg=Vj/(Ms*measure)
    st.success(f'**v_avg,j = {vavg:,.4f} {result_units}**')
    st.write(f'Vj = {Vj:,.3f} kips  |  Ms = {Ms:g}  |  Aw = {Aw_text}')
else:
    vavg=None
    st.info('Enter wall dimensions to complete Eq. 4-8.')

st.header('6. Calculation record')
notes=st.text_area('Assumptions / drawing references / notes')
record={
 'Direction':direction,'Building type':building_type,'Story band':story_band,'C':C,'Sa':Sa,'W (kips)':W,
 'V (kips)':V,'T (sec)':T,'k':k,'Level j':j,'Vj (kips)':Vj,'Wall category':wall_class,
 'Performance':perf,'Ms':Ms,'Aw':Aw_text,'vavg':vavg,'Result units':result_units,'Notes':notes}
st.download_button('Download calculation record',pd.DataFrame([record]).to_csv(index=False).encode(),'ASCE41_4433_calculation.csv','text/csv')
with st.expander('Table 4-7 C lookup used by this app'):
    st.dataframe(pd.DataFrame(C_TABLE,index=STORY_LABELS).T.rename_axis('Building type').reset_index(),hide_index=True,use_container_width=True)
