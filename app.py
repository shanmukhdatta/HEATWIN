"""Interactive simulation backed by the HEATWIN core."""
import streamlit as st
from heatwin.core import Parameters, simulate, metrics, fit_fopdt
from heatwin.diagnostics import predict_twin, residual_alarm

st.set_page_config(page_title='HEATWIN', layout='wide')
st.title('HEATWIN — heat exchanger digital twin')
st.caption('Illustrative simulated water-to-water exchanger; not a validated industrial safety system.')
with st.sidebar:
    mode = st.selectbox('Controller', ['P', 'PI', 'PID'])
    kp = st.number_input('Kp (fraction/°C)', 0., 1., .04, .01, format='%.3f')
    ki = st.number_input('Ki (fraction/(°C s))', 0., 1., .001, .001, format='%.3f') if mode != 'P' else 0.
    kd = st.number_input('Kd (fraction s/°C)', 0., 10., .08, .01) if mode == 'PID' else 0.
    sp = st.slider('Setpoint (°C)', 40., 65., 57.)
    ua = st.number_input('UA (W/K)', 1., 1000., 350.)
    fault = st.selectbox('Fault / disturbance at 300 s', ['None', 'Sensor bias +2 °C', 'Cold inlet −3 °C', 'Heat transfer −30%', 'Stuck actuator'])
    noise = st.slider('Sensor noise standard deviation (°C)', 0., 1., 0.)
    run = st.button('Run simulation', type='primary')
if run:
    data = simulate(p=Parameters(ua=ua), gains=(kp, ki, kd), setpoint=sp, noise=noise, bias=2 if fault.startswith('Sensor') else 0, disturbance=-3 if fault.startswith('Cold') else 0, degradation=.7 if fault.startswith('Heat') else 1., stuck=fault.startswith('Stuck'))
    training = simulate(open_loop=True)
    step = training[training.time >= 60]
    fitted = fit_fopdt(step.time.to_numpy()-60, (step.tc.to_numpy()-step.tc.iloc[0])/.1)
    data['twin'] = predict_twin(data.time, data.command, data.tc.iloc[0], *fitted)
    data['residual'] = data.measurement-data.twin
    data['alarm'] = residual_alarm(data.residual)
    st.caption('Twin: open-loop FOPDT fitted to a separate nominal valve step. Residuals also respond to disturbances and model mismatch.')
    st.line_chart(data.set_index('time')[[ 'tc', 'measurement', 'setpoint', 'twin']])
    st.write('Residual alarm:', bool(data.alarm.any()), ' | High temperature (> 65 °C):', bool((data.tc > 65).any()))
    st.line_chart(data.set_index('time')[[ 'residual']])
    st.line_chart(data.set_index('time')[['command', 'valve']])
    subset = data[data.time >= 60]
    st.json(metrics(subset.time.to_numpy(), subset.tc.to_numpy(), subset.setpoint.to_numpy(), subset.command.to_numpy()))
    st.download_button('Download CSV', data.to_csv(index=False), 'heatwin.csv', 'text/csv')
else:
    st.info('Choose parameters and run the simulation.')
