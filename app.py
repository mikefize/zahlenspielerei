import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import base64
import re
import matplotlib.colors as mc
import colorsys
import os

# --- KONFIGURATION & CLEAN LOOK ---
st.set_page_config(page_title="E-Bike Motoren Prüfstand", layout="wide")

hide_st_style = """
            <style>
            #MainMenu {visibility: hidden;}
            footer {visibility: hidden;}
            header {visibility: hidden;}
            </style>
            """
st.markdown(hide_st_style, unsafe_allow_html=True)

# --- HILFSFUNKTIONEN ---
def clean_column_names(df):
    df.columns = [re.sub(' +', ' ', c.strip()) for c in df.columns]
    return df

def lighten_color(color, amount=0.5):
    try:
        if isinstance(color, str) and color.startswith("rgb"):
            rgb = [int(x) for x in re.findall(r'\d+', color)]
            c_rgb = (rgb[0]/255.0, rgb[1]/255.0, rgb[2]/255.0)
        else:
            c_rgb = mc.to_rgb(color)
        c_hls = colorsys.rgb_to_hls(*c_rgb)
        new_lightness = max(0, min(1, amount * c_hls[1] + (1 - amount)))
        new_rgb = colorsys.hls_to_rgb(c_hls[0], new_lightness, c_hls[2])
        return mc.to_hex(new_rgb)
    except:
        return "#CCCCCC"

@st.cache_data
def load_data(filename, index_col_name=None, sep=";", decimal=","):
    try:
        # engine='python' ist robuster bei CSVs mit viel Text (Beschreibung)
        df = pd.read_csv(filename, sep=sep, decimal=decimal, engine='python')
        df = clean_column_names(df)
        
        if "15minuten" in filename or "20minuten" in filename:
            df.rename(columns={df.columns[0]: 'Time'}, inplace=True)
            df['Time'] = pd.to_datetime(df['Time'], format='%H:%M:%S', errors='coerce')
            df = df.dropna(subset=['Time'])
            return df

        if index_col_name:
            clean_idx = re.sub(' +', ' ', index_col_name.strip())
            if clean_idx in df.columns:
                df = df.dropna(subset=[clean_idx])
            else:
                # Fallback: Erste Spalte nehmen
                df = df.dropna(subset=[df.columns[0]])
        
        if index_col_name != "Modell": 
            # Versuche alles in Zahlen zu wandeln, außer Modell-Spalte
            # ignore errors, damit Text in Beschreibung nicht zu NaN wird
            cols = df.columns.drop(index_col_name) if index_col_name in df.columns else df.columns[1:]
            df[cols] = df[cols].apply(pd.to_numeric, errors='coerce')
            
        return df
    except FileNotFoundError:
        return None

def add_watermark(fig, x=0.5, y=0.5, size=0.6, opacity=0.15, xanchor="center", yanchor="middle"):
    try:
        with open("logo.png", "rb") as image_file:
            encoded_string = base64.b64encode(image_file.read()).decode()
        fig.add_layout_image(dict(source=f"data:image/png;base64,{encoded_string}", xref="paper", yref="paper", x=x, y=y, sizex=size, sizey=size, xanchor=xanchor, yanchor=yanchor, opacity=opacity, layer="below"))
    except: pass
    return fig

def lock_chart(fig):
    fig.update_xaxes(fixedrange=True)
    fig.update_yaxes(fixedrange=True)
    return fig

plotly_config = {
    'displayModeBar': True,
    'displaylogo': False,
    'modeBarButtonsToRemove': ['zoom2d', 'pan2d', 'select2d', 'lasso2d', 'zoomIn2d', 'zoomOut2d', 'autoScale2d', 'resetScale2d', 'hoverClosestCartesian', 'hoverCompareCartesian'],
    'toImageButtonOptions': {'format': 'png', 'filename': 'ebike_chart', 'height': 800, 'width': 1200, 'scale': 2}
}

# --- DATEN LADEN ---
df_leistung = load_data("leistung.csv", "Eingangsleistung")
df_kadenz = load_data("kadenz.csv", "Kadenz")
df_stammdaten = load_data("stammdaten.csv", "Modell")
df_therm_15 = load_data("15minuten.csv")
df_therm_20 = load_data("20minuten.csv")

if df_leistung is None:
    st.error("Datenbank nicht verfügbar.")
    st.stop()

df_thermik = None
if df_therm_15 is not None and df_therm_20 is not None:
    df_t15, df_t20 = df_therm_15.set_index('Time'), df_therm_20.set_index('Time')
    df_thermik = df_t20.combine_first(df_t15).reset_index().sort_values('Time').dropna(subset=['Time'])

motors_all = set(df_leistung.columns[1:]) | set(df_kadenz.columns[1:])
if df_thermik is not None: motors_all = motors_all | set([c for c in df_thermik.columns if c != 'Time'])
all_motors = sorted(list(motors_all))

colors_palette = px.colors.qualitative.Bold + px.colors.qualitative.Prism + px.colors.qualitative.Vivid
motor_color_map = {motor: colors_palette[i % len(colors_palette)] for i, motor in enumerate(all_motors)}

# Indexierung robuster machen
try:
    idx_250 = (df_leistung[df_leistung.columns[0]] - 250).abs().idxmin()
    ref_power_map = df_leistung.loc[idx_250].to_dict()
except:
    ref_power_map = {}

if 'active_view' not in st.session_state: st.session_state.active_view = "Leistungskurven"
if 'stored_selection' not in st.session_state: st.session_state.stored_selection = all_motors 
if not st.session_state.stored_selection: st.session_state.stored_selection = all_motors

def update_selection(): st.session_state.stored_selection = st.session_state.widget_selection

st.sidebar.header("Navigation")
def nav_button(label, view_name):
    btn_type = "primary" if st.session_state.active_view == view_name else "secondary"
    if st.sidebar.button(label, key=view_name, type=btn_type, use_container_width=True):
        st.session_state.active_view = view_name
        st.rerun()
nav_button("Leistungskurven (Input)", "Leistungskurven")
nav_button("Kadenz-Verlauf (RPM)", "Kadenz-Verlauf")
nav_button("Thermisches Derating", "Thermik")
st.sidebar.markdown("---")
nav_button("Motor-Steckbriefe", "Motor-Steckbriefe")

current_topic = st.session_state.active_view

# ==============================================================================
# MOTOR STECKBRIEFE
# ==============================================================================
if current_topic == "Motor-Steckbriefe":
    st.title("📝 Motor-Steckbrief")
    c_sel, _ = st.columns([1, 2])
    with c_sel: selected_single = st.selectbox("Motor wählen:", all_motors)
    st.markdown("---")
    
    meta_data_found = False
    
    if df_stammdaten is not None:
        meta = df_stammdaten[df_stammdaten["Modell"] == selected_single]
        if not meta.empty:
            meta_data_found = True
            def gv(c): return meta.iloc[0][c] if c in meta.columns else "-"

            # 1. BESCHREIBUNG (Ganz oben, prominent)
            desc = gv("Beschreibung")
            if desc != "-" and pd.notna(desc):
                st.info(desc) # Blaue Box
            
            # 2. KENNZAHLEN
            c1, c2, c3 = st.columns(3)
            # Hersteller aus Namen raten, falls nicht in CSV
            hersteller = selected_single.split(" ")[0] 
            
            with c1: st.metric("Hersteller", hersteller)
            with c2: st.metric("Gewicht", f"{gv('Gewicht (kg)')} kg")
            with c3: st.metric("Max. Drehmoment", f"{gv('Max. Drehmoment (Nm)')} Nm")

            # Link zur Herstellerseite
            link_web = gv("Link_Hersteller")
            if link_web != "-" and str(link_web).startswith("http"):
                st.caption(f"[🌐 Zur Herstellerseite]({link_web})")
            
            st.markdown("---")

    # 3. DIAGRAMME
    st.subheader("Messdaten")
    cL, cK, cT = st.columns(3) # Jetzt 3 Spalten für Thermik
    motor_color = motor_color_map.get(selected_single, "blue")
    
    with cL:
        if selected_single in df_leistung.columns:
            fig = px.line(df_leistung, x=df_leistung.columns[0], y=selected_single, title="Leistungskurve")
            fig.update_traces(fill='tozeroy', line_color=motor_color)
            fig = lock_chart(add_watermark(fig))
            st.plotly_chart(fig, use_container_width=True, config=plotly_config)
            
    with cK:
        if selected_single in df_kadenz.columns:
            fig = px.line(df_kadenz, x=df_kadenz.columns[0], y=selected_single, title="Kadenzverlauf")
            fig.update_traces(fill='tozeroy', line_color=motor_color)
            fig = lock_chart(add_watermark(fig))
            st.plotly_chart(fig, use_container_width=True, config=plotly_config)
            
    with cT:
        # Thermik (15 min Ausschnitt)
        if df_thermik is not None and selected_single in df_thermik.columns:
             start_t = df_thermik["Time"].min()
             end_t = start_t + pd.Timedelta(minutes=15)
             df_15 = df_thermik[(df_thermik["Time"] >= start_t) & (df_thermik["Time"] <= end_t)]
             
             fig = px.line(df_15, x="Time", y=selected_single, title="Thermik (15 min)")
             fig.update_traces(fill='tozeroy', line_color=motor_color)
             fig.update_xaxes(tickformat="%M:%S")
             fig = lock_chart(add_watermark(fig))
             st.plotly_chart(fig, use_container_width=True, config=plotly_config)

    # 4. ZUSATZDATEN (Support)
    support_filename = f"support_{selected_single}.csv"
    if os.path.exists(support_filename):
        df_support = load_data(support_filename)
        if df_support is not None and not df_support.empty:
            st.subheader("Unterstützungsstufen")
            fig_sup = px.line(df_support, x=df_support.columns[0], y=df_support.columns[1:])
            fig_sup = lock_chart(add_watermark(fig_sup))
            st.plotly_chart(fig_sup, use_container_width=True, config=plotly_config)

    # 5. MEDIEN (Ganz unten)
    if meta_data_found:
        art, yt = gv("Link_Artikel"), gv("Link_Youtube")
        has_art = str(art).startswith("http")
        has_yt = str(yt).startswith("http")
        
        if has_art or has_yt:
            st.markdown("---")
            st.subheader("Mehr erfahren")
            m1, m2, m3 = st.columns([1, 1, 2]) 
            with m1:
                if has_yt:
                    st.markdown("**Video-Test:**")
                    st.video(yt)
            with m2:
                if has_art:
                    st.markdown("**Testbericht:**")
                    st.write("Alle Details und Fazit im Artikel.")
                    st.link_button("📄 Zum Testbericht", art, type="primary") 

# ==============================================================================
# VERGLEICHS-TOOL
# ==============================================================================
else:
    st.title(f"📊 Vergleich: {current_topic}")
    with st.container():
        c_mot, c_set = st.columns([3, 1])
        with c_mot:
            st.multiselect("Motoren auswählen:", options=all_motors, default=st.session_state.stored_selection, key="widget_selection", on_change=update_selection)
            selected_motors = st.session_state.stored_selection
        df_chart = None
        x_col, x_label, y_label = "", "", "Leistung (Watt)"
        with c_set:
            if current_topic == "Leistungskurven":
                min_v, max_v = int(df_leistung.iloc[:, 0].min()), int(df_leistung.iloc[:, 0].max())
                val = st.slider("Input (Watt)", min_v, max_v, (min_v, max_v))
                mask = (df_leistung.iloc[:, 0] >= val[0]) & (df_leistung.iloc[:, 0] <= val[1])
                df_chart = df_leistung.loc[mask]
                x_col, x_label = df_leistung.columns[0], "Eingangsleistung (Watt)"
            elif current_topic == "Kadenz-Verlauf":
                min_v, max_v = int(df_kadenz.iloc[:, 0].min()), int(df_kadenz.iloc[:, 0].max())
                val = st.slider("Kadenz (RPM)", min_v, max_v, (min_v, max_v))
                mask = (df_kadenz.iloc[:, 0] >= val[0]) & (df_kadenz.iloc[:, 0] <= val[1])
                df_chart = df_kadenz.loc[mask]
                x_col, x_label = df_kadenz.columns[0], "Kadenz (RPM)"
            elif current_topic == "Thermik":
                if df_thermik is not None:
                    unit = st.radio("Einheit:", ["% Derating (Relativ)", "Absolute Leistung (Watt)"])
                    df_chart = df_thermik.copy()
                    x_col, x_label = "Time", "Zeit (mm:ss)"
                    if "Watt" in unit:
                        y_label = "Leistung (Watt bei 250W Input)"
                        for m in selected_motors:
                            if m in df_chart.columns and m in ref_power_map:
                                df_chart[m] = (df_chart[m] / 100) * ref_power_map[m]
                    else: y_label = "Leistung (% vom Startwert)"
                else: st.warning("Keine Thermik-Daten.")
    st.markdown("---")
    if not selected_motors: st.stop()
    valid_motors = [m for m in selected_motors if m in df_chart.columns]
    if valid_motors:
        fig = px.line(df_chart, x=x_col, y=valid_motors, labels={x_col: x_label, "value": y_label, "variable": "Motor"}, color_discrete_map=motor_color_map)
        if current_topic == "Thermik": fig.update_xaxes(tickformat="%M:%S")
        
        fig = add_watermark(fig, size=0.6, opacity=0.15)
        fig = lock_chart(fig) 
        fig.update_layout(hovermode="x unified", height=600, legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
        st.plotly_chart(fig, use_container_width=True, config=plotly_config)
        
        csv = df_chart[[x_col] + valid_motors].to_csv(index=False, sep=";", decimal=",").encode('utf-8')
        st.download_button("💾 CSV Export", csv, "export.csv", "text/csv")
        
        if current_topic != "Thermik":
            st.markdown("### 🔍 Detail-Vergleich")
            c1, c2 = st.columns([1, 2])
            min_c, max_c = int(df_chart[x_col].min()), int(df_chart[x_col].max())
            with c1:
                st.markdown(" ")
                target = st.slider(f"Punkt ({x_label})", min_c, max_c, int((min_c+max_c)/2))
            with c2:
                row = df_chart.loc[(df_chart[x_col] - target).abs().idxmin()]
                bar_data = pd.DataFrame([{"Motor": m, "Wert": row[m]} for m in valid_motors])
                fig_bar = px.bar(bar_data, x="Wert", y="Motor", color="Motor", orientation='h', text_auto='.1f', color_discrete_map=motor_color_map)
                fig_bar.update_yaxes(categoryorder='total ascending')
                dynamic_height = max(400, len(valid_motors) * 40)
                fig_bar = lock_chart(fig_bar)
                fig_bar.update_layout(height=dynamic_height, showlegend=False)
                st.plotly_chart(add_watermark(fig_bar, x=1, y=0, size=0.15, opacity=0.3, xanchor="right", yanchor="bottom"), use_container_width=True, config=plotly_config)
        else:
            st.markdown("### 📉 Durchschnitt & Minimum (erste 15 Min)")
            start_t = df_chart[x_col].min()
            end_t = start_t + pd.Timedelta(minutes=15)
            df_15 = df_chart[(df_chart[x_col] >= start_t) & (df_chart[x_col] <= end_t)]
            
            data_list = []
            for m in valid_motors:
                base_c = motor_color_map.get(m, "#000000")
                light_c = lighten_color(base_c, 0.5)
                data_list.append({"Motor": m, "Avg": df_15[m].mean(), "Min": df_15[m].min(), "ColorAvg": base_c, "ColorMin": light_c})
            
            df_res = pd.DataFrame(data_list)
            if not df_res.empty:
                df_res = df_res.sort_values(by="Avg", ascending=True)
                fig_bar = go.Figure()
                fig_bar.add_trace(go.Bar(y=df_res["Motor"], x=df_res["Avg"], orientation='h', name="Durchschnitt", marker_color=df_res["ColorAvg"], text=df_res["Avg"].round(1), textposition='auto'))
                fig_bar.add_trace(go.Bar(y=df_res["Motor"], x=df_res["Min"], orientation='h', name="Minimum", marker_color=df_res["ColorMin"], text=df_res["Min"].round(1), textposition='auto'))
                
                fig_bar = lock_chart(fig_bar)
                dynamic_height = 200 + (len(valid_motors) * 50)
                fig_bar.update_layout(barmode='group', height=dynamic_height, xaxis_title=y_label, legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1), margin=dict(l=0, r=0, t=30, b=0))
                st.plotly_chart(add_watermark(fig_bar, x=1, y=0, size=0.15, opacity=0.3, xanchor="right", yanchor="bottom"), use_container_width=True, config=plotly_config)

    else: st.info("Keine Daten.")