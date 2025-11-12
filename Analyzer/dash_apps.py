import base64
import io
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import dash
from dash import dcc, html, Input, Output, State, exceptions
import dash_bootstrap_components as dbc
from django_plotly_dash import DjangoDash

# --- Librerías de Procesamiento ---
import neurokit2 as nk

# --- [INICIO] Carga de Modelo TensorFlow ---
import tensorflow as tf
import os
from django.conf import settings 

# 1. Asegúrate que la ruta sea correcta
MODEL_FILE_PATH = os.path.join(settings.BASE_DIR, 'Analyzer', 'models', 'ecg_arrhythmia.hdf5') 

MODELO_NN = None
try:
    if os.path.exists(MODEL_FILE_PATH):
        MODELO_NN = tf.keras.models.load_model(MODEL_FILE_PATH)
        print("="*50)
        print(f"Modelo de NN cargado exitosamente desde: {MODEL_FILE_PATH}")
        MODELO_NN.summary()
        print("="*50)
    else:
        print(f"ERROR: No se encontró el archivo del modelo en {MODEL_FILE_PATH}")
except Exception as e:
    print(f"ERROR AL CARGAR EL MODELO: {e}")
# --- [FIN] Carga de Modelo TensorFlow ---


# 1. Creamos la app de Dash
app = DjangoDash('CardiacAnalyzerApp',
                 external_stylesheets=[dbc.themes.BOOTSTRAP],
                 # Solución para problemas de renderizado en versiones antiguas de Plotly.js
                 external_scripts=['https://cdn.plot.ly/plotly-2.32.0.min.js'])


# --- Componentes Reutilizables ---
def create_kpi_card(title, value_id, color="success"):
    return dbc.Card(
        dbc.CardBody([
            html.H4(title, className="card-title"),
            html.H2(id=value_id, className="card-text text-" + color),
        ]),
        className="text-center m-2"
    )

# 2. Definimos el Layout (la apariencia)
app.layout = html.Div(
    style={'width': '100%', 'height': '100%', 'display': 'flex', 'flexDirection': 'column'},
    children=[
        dbc.Container(fluid=True, children=[
            # --- Almacenes de Datos ---
            dcc.Store(id='full-dataframe-store'),
            dcc.Store(id='signal-data-store'), 
            dcc.Store(id='classification-store'),
            dcc.Store(id='morphology-store'), 

            # --- Título ---
            html.H1("Panel de Control de Análisis Cardíaco", style={'textAlign': 'center', 'margin': '20px'}),
            
            # --- Sección de Carga ---
            dbc.Card(
                dbc.CardBody([
                    dbc.Row([
                        dbc.Col(
                            dcc.Upload(
                                id='upload-data',
                                children=html.Div(['Arrastra y suelta o ', html.A('Selecciona tu archivo ')]),
                                style={
                                    'width': '100%', 'height': '60px', 'lineHeight': '60px',
                                    'borderWidth': '1px', 'borderStyle': 'dashed',
                                    'borderRadius': '5px', 'textAlign': 'center'
                                },
                                accept='.csv, .xlsx, .xls'
                            ), width=6
                        ),
                        dbc.Col(
                            dcc.Input(
                                id='sampling-rate-input',
                                type='number',
                                placeholder='Frecuencia (ej: 125 Hz)',
                                value=188, # Valor por defecto
                                style={'width': '100%', 'height': '60px'}
                            ), width=3
                        ),
                        dbc.Col(
                            dcc.Input(
                                id='row-index-input',
                                type='number',
                                placeholder='N° de Fila (ej: 0)',
                                value=0, # Analiza la primera fila por defecto
                                min=0,
                                step=1,
                                style={'width': '100%', 'height': '60px'}
                            ), width=3
                        ),
                    ]),
                    # ESTE COMPONENTE MUESTRA EL MENSAJE DE ÉXITO DE LA CARGA
                    html.Div(id='filename-output', style={'margin': '10px 0', 'fontWeight': 'bold', 'color': 'green'})
                ]),
                className="mb-3"
            ),
            
            dbc.Alert(id='error-output', color="danger", is_open=False, duration=4000),

            # --- Pestañas (Tabs) para el análisis ---
            dcc.Tabs(id="analysis-tabs", children=[
                dcc.Tab(label='Señal Cruda vs. Filtrada', children=[
                    dbc.Row([
                        dbc.Col(dcc.Graph(id='raw-signal-graph', style={'height': '350px'}), width=12),
                    ]),
                    dbc.Row([
                        dbc.Col(dcc.Graph(id='filtered-signal-graph', style={'height': '350px'}), width=12),
                    ]),
                ]),
                dcc.Tab(label='Detección de Ondas y Morfología', children=[
                    # Gráfico de picos y ondas
                    dcc.Graph(id='peaks-graph', style={'height': '500px'}), 
                    
                    # Nuevos KPIs de morfología
                    html.H3("Métricas Morfológicas del Latido", className="mt-4 text-center"),
                    dbc.Row([
                        dbc.Col(create_kpi_card("Duración QRS (ms)", "kpi-qrs-duration", "info"), width=4),
                        dbc.Col(create_kpi_card("Amplitud R (mV/uV)", "kpi-r-amplitude", "danger"), width=4),
                        dbc.Col(create_kpi_card("Pendiente ST (mV/s)", "kpi-st-slope", "warning"), width=4),
                    ], className="mt-4"),
                    # Necesitamos mantener el componente poincare-graph en el layout 
                    # para que el callback de morfología no falle (se dejó vacío en el layout)
                    html.Div(dcc.Graph(id='poincare-graph', style={'display': 'none'})) 
                ]),
                dcc.Tab(label='Clasificación del Modelo & Métricas Clave', children=[
                    dbc.Row([
                        # Las IDs de los KPIs son: kpi-r-peak, kpi-segment-length, kpi-classification
                        dbc.Col(create_kpi_card("Pico R (Sample)", "kpi-r-peak"), width=4), 
                        dbc.Col(create_kpi_card("Longitud Segmento", "kpi-segment-length"), width=4),
                        dbc.Col(create_kpi_card("Clasificación Modelo", "kpi-classification", "primary"), width=4),
                    ], className="mt-4"),
                    html.H3("Probabilidades de Clasificación del Modelo", className="mt-4 text-center"),
                    dcc.Graph(id='classification-probs-graph')
                ]),
            ])
        ])
    ]
)

# --- [INICIO] Función de tu Modelo (Clasificación Directa) ---
def run_my_nn_model(signal_raw):
    # <<< CLASES TRADUCIDAS AL ESPAÑOL >>>
    CLASSES_DEL_MODELO = [
        "Normal", 
        "Contracción Auricular Prematura (CAP)",
        "Contracción Ventricular Prematura (CVP)",
        "Fusión (Ventricular y Normal)",
        "Fusión (Marcapasos y Normal)"
    ]
    
    if MODELO_NN is None:
        return "ERROR: Modelo no cargado", [0.2]*5, CLASSES_DEL_MODELO

    try:
        SEGMENT_LENGTH = 187 
        
        if len(signal_raw) != SEGMENT_LENGTH:
             return f"Error: Longitud incorrecta ({len(signal_raw)}). Esperado: {SEGMENT_LENGTH}", [0.2]*5, CLASSES_DEL_MODELO

        # 2. APLICAR NORMALIZACIÓN MIN-MAX (CRÍTICO)
        min_val = np.min(signal_raw)
        max_val = np.max(signal_raw)
        
        if max_val - min_val > 0:
            segment_normalized = (signal_raw - min_val) / (max_val - min_val)
        else:
            segment_normalized = signal_raw * 0.0 
            
        # 3. Reshape para la CNN (1 segmento, 187 puntos, 1 canal)
        segment_np = segment_normalized.reshape(1, SEGMENT_LENGTH, 1) 
        
        # 4. Predicción
        predictions = MODELO_NN.predict(segment_np, verbose=0)
        
        probabilities = predictions[0]
        predicted_class_index = np.argmax(probabilities)
        predicted_class_string = CLASSES_DEL_MODELO[predicted_class_index]
        
        return predicted_class_string, np.round(probabilities, 4).tolist(), CLASSES_DEL_MODELO

    except Exception as e:
        print(f"Error durante la predicción: {e}")
        return f"Error de NN: {e}", [0.2]*5, CLASSES_DEL_MODELO
# --- [FIN] Función de tu Modelo (Clasificación Directa) ---


# --- Callback 1: Cargar y Almacenar el Archivo (OK) ---
@app.callback(
    Output('full-dataframe-store', 'data'),
    Output('filename-output', 'children'),
    Output('error-output', 'is_open'),
    Output('error-output', 'children'),
    Input('upload-data', 'contents'),
    State('upload-data', 'filename'),
    prevent_initial_call=True
)
def cache_uploaded_file(contents, filename):
    if contents is None:
        raise exceptions.PreventUpdate

    content_type, content_string = contents.split(',')
    decoded = base64.b64decode(content_string)
    
    try:
        if 'csv' in filename:
            df = pd.read_csv(io.StringIO(decoded.decode('utf-8')), header=None)
        elif 'xls' in filename or 'xlsx' in filename:
            df = pd.read_excel(io.BytesIO(decoded), header=None)
        else:
            return None, "", True, "Error: Formato de archivo no soportado. Usa .csv, .xls, o .xlsx."
        
        print(f"!!! ÉXITO DE CARGA: {filename} ({len(df)} filas, {len(df.columns)} columnas) !!!")

        return df.to_json(orient='split'), f"Archivo cargado: {filename}. Filas disponibles: 0 a {len(df)-1} (Total de columnas: {len(df.columns)})", False, ""

    except Exception as e:
        print(f"Error cargando el archivo: {e}")
        return None, "", True, f"Error al leer el archivo: {e}"


# --- Callback 2: Procesamiento Principal (Segmento Único con Morfología) ---
@app.callback(
    Output('signal-data-store', 'data'),
    Output('classification-store', 'data'),
    Output('morphology-store', 'data'), 
    Output('error-output', 'is_open', allow_duplicate=True),
    Output('error-output', 'children', allow_duplicate=True),
    Input('full-dataframe-store', 'data'),
    Input('row-index-input', 'value'),
    State('sampling-rate-input', 'value'),
    prevent_initial_call=True
)
def process_selected_row(df_json, row_index, sampling_rate):
    
    if df_json is None or row_index is None:
        raise exceptions.PreventUpdate

    if sampling_rate is None or sampling_rate <= 0:
        return None, None, None, True, "Error: La frecuencia de muestreo debe ser un número positivo."

    try:
        df = pd.read_json(df_json, orient='split')
        
        # Leemos solo los 187 puntos, ignorando la última columna si existe (la etiqueta)
        signal_raw = df.iloc[row_index, 0:187].values.astype(float) 
        
        # --- PROCESAMIENTO NeuroKit2 ---
        
        # 1. Limpieza (Bypass)
        signal_cleaned = signal_raw 
        print("DIAGNÓSTICO NK2: Señal corta. Usando señal cruda como limpia.")

        # 2. Detección de Pico R (forzada al centro)
        r_peak_index = 187 // 2 # Usar centro (ej: índice 93)
        
        # 3. Delineación de Ondas (Estimación Morfológica)
        
        # Estimaciones de Duración para 125 Hz (8ms por muestra):
        QRS_HALF_DURATION_SAMPLES = 8 
        T_WAVE_START_OFFSET = 15
        T_WAVE_END_OFFSET = 35
        
        Q_onset = r_peak_index - QRS_HALF_DURATION_SAMPLES 
        S_offset = r_peak_index + QRS_HALF_DURATION_SAMPLES 
        
        # Asignamos valores fijos para la delineación (solo para el gráfico)
        waves_dict_plot = {
            'ECG_R_Peaks': np.array([r_peak_index]),
            'ECG_Q_Onsets': np.array([Q_onset]),
            'ECG_S_Offsets': np.array([S_offset]),
            'ECG_T_Onsets': np.array([r_peak_index + T_WAVE_START_OFFSET]),
            'ECG_T_Offsets': np.array([r_peak_index + T_WAVE_END_OFFSET]),
            'ECG_P_Onsets': np.array([r_peak_index - 25]), # Estimación visual
            'ECG_P_Offsets': np.array([r_peak_index - 15]) # Estimación visual
        }

        # 4. Clasificación CNN
        classification, probabilities, classes = run_my_nn_model(signal_raw)
        
        print(f"!!! ÉXITO DE PROCESAMIENTO de la Fila {row_index}. Clasificación: {classification} !!!")
        
        # --- PREPARACIÓN DE STORES ---
        
        # Generar DataFrame para gráficos
        processed_df = pd.DataFrame({
            "Time": np.arange(len(signal_raw)) / sampling_rate, 
            "ECG_Raw": signal_raw,
            "ECG_Clean": signal_cleaned
        })
        
        # Cálculo de Métricas Morfológicas usando los índices estimados
        
        qrs_duration = (S_offset - Q_onset) * 1000 / sampling_rate 
        r_amplitude = signal_cleaned[r_peak_index]
        
        # Cálculo de Pendiente ST (usando el punto J y el inicio de T estimado)
        j_point_val = signal_cleaned[S_offset]
        t_onset_val = signal_cleaned[r_peak_index + T_WAVE_START_OFFSET]
        
        delta_t = (T_WAVE_START_OFFSET) / sampling_rate
        st_slope_val = (t_onset_val - j_point_val) / delta_t
        
        # Limpieza de datos
        safe_waves = {k: float(v[0]) for k, v in waves_dict_plot.items()}
        
        data_to_store = {
            'processed_df_json': processed_df.to_json(orient='split'),
            'rr_intervals_ms': [], 
            'hrv_bpm': 0.0, 
            'hrv_rmssd': 0.0,
            'r_peak_index': r_peak_index
        }
        
        classification_data = {
            'class': classification,
            'probabilities': probabilities,
            'classes': classes
        }
        
        morphology_data = {
            'waves': safe_waves,
            'qrs_duration': f"{qrs_duration:.2f}",
            'r_amplitude': f"{r_amplitude:.3f}",
            'st_slope': f"{st_slope_val:.3f}"
        }

        return data_to_store, classification_data, morphology_data, False, ""

    except IndexError:
        return None, None, None, True, f"Error: La fila {row_index} no existe en el archivo."
    except Exception as e:
        print(f"Error procesando la señal: {e}")
        return None, None, None, True, f"Error al procesar la fila {row_index}: {e}"


# --- Función Helper para Figuras Vacías (SIN CAMBIOS) ---
def create_empty_fig(message="Carga un archivo y selecciona una fila para ver el análisis"):
    fig = go.Figure()
    fig.update_layout(
        xaxis =  { "visible": False },
        yaxis = { "visible": False },
        annotations = [{
            "text": message, "xref": "paper", "yref": "paper",
            "showarrow": False, "font": { "size": 16 }
        }]
    )
    return fig

# --- Callbacks de Visualización de Señal (SIN CAMBIOS Mayores) ---
@app.callback(
    Output('raw-signal-graph', 'figure'),
    Output('filtered-signal-graph', 'figure'),
    Input('signal-data-store', 'data')
)
def update_signal_graphs(data):
    if data is None:
        return create_empty_fig(), create_empty_fig()
    
    try:
        df = pd.read_json(data['processed_df_json'], orient='split')
    except Exception:
        return create_empty_fig("Error: No se pudo cargar el DataFrame de señal."), create_empty_fig()
    
    # Rango de visualización fijo para segmentos de 187p (mejor presentación)
    y_range = [df['ECG_Raw'].min() - 0.1, df['ECG_Raw'].max() + 0.1]
    
    # Figura Cruda
    fig_raw = go.Figure(data=[
        go.Scatter(x=df['Time'], y=df['ECG_Raw'], mode='lines+markers', name='Señal Cruda', 
                   line=dict(width=3), marker=dict(size=6))
    ])
    fig_raw.update_layout(title="Señal Cruda", xaxis_title="Tiempo (s)", yaxis_title="Amplitud", yaxis=dict(range=y_range))
    
    # Figura Filtrada (Muestra la señal usada para el modelo)
    fig_filtered = go.Figure(data=[
        go.Scatter(x=df['Time'], y=df['ECG_Clean'], mode='lines+markers', name='Señal Usada (Limpia)', 
                   line=dict(color='orange', width=3), marker=dict(size=6))
    ])
    fig_filtered.update_layout(title="Señal Filtrada", xaxis_title="Tiempo (s)", yaxis_title="Amplitud", yaxis=dict(range=y_range))
    
    return fig_raw, fig_filtered

# --- Callback de Morfología y Ondas (¡NUEVO Y MEJORADO!) ---
@app.callback(
    # Outputs de la pestaña Morfología/Ondas
    Output('peaks-graph', 'figure'),
    Output('poincare-graph', 'figure'),
    Output('kpi-qrs-duration', 'children'),
    Output('kpi-r-amplitude', 'children'),
    Output('kpi-st-slope', 'children'),
    Input('signal-data-store', 'data'),
    Input('morphology-store', 'data')
)
def update_morphology_and_hrv_graphs(data, morphology_data):
    # Ya que eliminamos poincare-graph del layout, debemos asegurar que el Output 
    # de esta función coincida con los 5 outputs de arriba, incluyendo el fantasma.
    
    if data is None or morphology_data is None:
        # Retornamos valores seguros y un gráfico vacío para el fantasma
        return create_empty_fig(), create_empty_fig("HRV no aplica a un solo latido."), "-", "-", "-"
        
    try:
        df = pd.read_json(data['processed_df_json'], orient='split')
        waves = morphology_data.get('waves', {})
    except Exception:
        return create_empty_fig("Error al cargar datos."), create_empty_fig("HRV no aplica a un solo latido."), "-", "-", "-"

    # Figura Picos y Ondas
    fig_peaks = go.Figure(data=[
        go.Scatter(x=df['Time'], y=df['ECG_Clean'], mode='lines', name='Señal Analizada', line=dict(width=2, color='darkblue')), 
    ])
    
    # Definición de las ondas y sus colores
    wave_markers = {
        'ECG_R_Peaks': {'name': 'Pico R', 'color': 'red', 'symbol': 'star'},
        'ECG_P_Onsets': {'name': 'P-inicio (Est.)', 'color': 'darkgreen', 'symbol': 'circle-open'},
        'ECG_P_Offsets': {'name': 'P-fin (Est.)', 'color': 'green', 'symbol': 'circle'},
        'ECG_Q_Onsets': {'name': 'QRS-inicio (Est.)', 'color': 'orange', 'symbol': 'x'},
        'ECG_S_Offsets': {'name': 'QRS-fin (Est.)', 'color': 'purple', 'symbol': 'diamond'},
        'ECG_T_Onsets': {'name': 'T-inicio (Est.)', 'color': 'brown', 'symbol': 'square'},
        'ECG_T_Offsets': {'name': 'T-fin (Est.)', 'color': 'black', 'symbol': 'square-open'}
    }
    
    # Añadir marcadores de ondas al gráfico
    for key, marker_props in wave_markers.items():
        idx = waves.get(key)
        # Solo dibujamos si el índice es un número válido y está en el DataFrame
        if idx is not None and np.isfinite(idx) and int(idx) in df.index:
            idx = int(idx)
            fig_peaks.add_trace(go.Scatter(
                x=[df.loc[idx, 'Time']], 
                y=[df.loc[idx, 'ECG_Clean']], 
                mode='markers', 
                name=marker_props['name'], 
                marker=dict(color=marker_props['color'], size=10, symbol=marker_props['symbol'], line=dict(width=1, color='black'))
            ))

    fig_peaks.update_layout(
        title="Delineación de Ondas P, QRS y T",
        xaxis_title="Tiempo (s)", 
        yaxis_title="Amplitud",
        yaxis=dict(range=[df['ECG_Clean'].min() - 0.1, df['ECG_Clean'].max() + 0.1]),
        showlegend=True
    )
    
    # El gráfico de Poincaré se deja vacío y con mensaje
    fig_poincare = create_empty_fig("El gráfico de Poincaré (HRV) no aplica a un único latido de ECG.")
    
    # Retorno de KPIs morfológicos (los 5 outputs declarados)
    return fig_peaks, fig_poincare, \
           f"{morphology_data['qrs_duration']} ms", \
           f"{morphology_data['r_amplitude']}", \
           f"{morphology_data['st_slope']}"

# --- Callback de Clasificación y Métricas Base (SIN CAMBIOS Mayores) ---
@app.callback(
    # Estos son los 3 outputs de la pestaña Clasificación
    Output('kpi-r-peak', 'children'), 
    Output('kpi-segment-length', 'children'), 
    Output('kpi-classification', 'children'),
    Output('classification-probs-graph', 'figure'),
    Input('signal-data-store', 'data'),
    Input('classification-store', 'data')
)
def update_classification_tab(signal_data, classification_data):
    if signal_data is None or classification_data is None:
        return "-", "-", "-", create_empty_fig()
    
    # KPIs de la pestaña 'Clasificación'
    segment_length = f"{len(pd.read_json(signal_data['processed_df_json'], orient='split'))} pts"
    classification = classification_data['class']
    
    # Usamos los KPIs de BPM/RMSSD para mostrar el tamaño y la ubicación del pico R
    kpi_r_peak = f"{signal_data['r_peak_index']} pts"
    
    probs = classification_data['probabilities']
    classes = classification_data['classes']
    
    fig_probs = go.Figure(data=[
        go.Bar(x=classes, y=probs, marker_color='rgb(55, 83, 109)')
    ])
    fig_probs.update_layout(
        title="Probabilidades de Clasificación del Modelo",
        yaxis_title="Probabilidad"
    )
    
    # Retornamos los 4 outputs
    return kpi_r_peak, segment_length, classification, fig_probs