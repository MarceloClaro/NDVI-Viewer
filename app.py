import streamlit as st
import ee
import geemap
import folium
from folium import WmsTileLayer
from streamlit_folium import folium_static
from datetime import datetime, timedelta
import json

# Initializing the Earth Engine library
@st.cache_data(persist=True)
def ee_authenticate(token_name="EARTHENGINE_TOKEN"):
    geemap.ee_initialize(token_name=token_name)

# Earth Engine drawing method setup
def add_ee_layer(self, ee_image_object, vis_params, name):
    map_id_dict = ee.Image(ee_image_object).getMapId(vis_params)
    layer = folium.raster_layers.TileLayer(
        tiles=map_id_dict['tile_fetcher'].url_format,
        attr='Map Data &copy; <a href="https://earthengine.google.com/">Google Earth Engine</a>',
        name=name,
        overlay=True,
        control=True
    )
    layer.add_to(self)
    return layer

# Configuring Earth Engine display rendering method in Folium
folium.Map.add_ee_layer = add_ee_layer

# Main header title
st.title('Earth Engine Streamlit App')

# Uplaod function 
def upload_files_proc(upload_files):
    geometry_aoi_list = []
    for upload_file in upload_files:
        bytes_data = upload_file.read()
        # Parse GeoJSON data
        geojson_data = json.loads(bytes_data)
        # Extract the coordinates from the GeoJSON data
        coordinates = geojson_data['features'][0]['geometry']['coordinates']
        # Creating gee geometry object based on coordinates
        geometry = ee.Geometry.Polygon(coordinates)
        # Adding geometry to the list
        geometry_aoi_list.append(geometry)
    # Combine multiple geometries from same/different files
    if geometry_aoi_list:
        geometry_aoi = ee.Geometry.MultiPolygon(geometry_aoi_list)
    else:
        # Set default geometry if no file uploaded
        geometry_aoi = ee.Geometry.Point([27.98, 36.13])
    return geometry_aoi

# Main function to run the Streamlit app
def main():
    ee_authenticate(token_name="EARTHENGINE_TOKEN")
    #### User input section START

    ## File upload
    # User input GeoJSON file
    upload_files = st.file_uploader("Choose a GeoJSON file", accept_multiple_files=True)
    # calling upload files function
    geometry_aoi = upload_files_proc(upload_files)

    ## Time range inpui
    # time input goes here
    # Get user input for the date range using st.date_input
    col1, col2 = st.columns(2)
    start_date = col1.date_input("Start Date", datetime(2023, 2, 10))
    end_date = col2.date_input("End Date", datetime(2023, 2, 20))

    # converting date input gee filter format before passing it in
    start_date = start_date.strftime('%Y-%m-%d')
    end_date = end_date.strftime('%Y-%m-%d')


    #### User input section END

    #### Map section START
    # Setting up main map
    m = folium.Map(location=[36.40, 2.80], tiles='Open Street Map', zoom_start=10, control_scale=True)

    ### BASEMAPS
    ## Primary basemaps
    # CartoDB Dark Matter basemap
    b1 = folium.TileLayer('cartodbdark_matter', name='Dark Matter Basemap')
    b1.add_to(m)

    ## WMS tiles basemaps
    # OSM CyclOSM basemap 
    b2 = WmsTileLayer(
        url=('https://{s}.tile-cyclosm.openstreetmap.fr/cyclosm/{z}/{x}/{y}.png'),
        layers=None,
        name='Topography Basemap', # layer name to display on layer panel
        attr='Topography Map',
        show=False
    )
    b2.add_to(m)

    #### Map section END

    #### Satellite imagery Processing Section START
    # Image collection
    collection = ee.ImageCollection('COPERNICUS/S2_SR') \
    .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 100)) \
    .filterDate(start_date, end_date) \
    .filterBounds(geometry_aoi)

    # clipping the main collection to the aoi geometry
    clipped_collection = collection.map(lambda image: image.clip(geometry_aoi).divide(10000))
    
    # setting a sat_imagery variable that could be used for various processes later on (tci, ndvi... etc)
    sat_imagery = clipped_collection.median() 

    ## TCI (True Color Imagery)
    # Clipping the image to the area of interest "aoi"
    tci_image = sat_imagery

    # TCI image visual parameters
    tci_params = {
      'bands': ['B4', 'B3', 'B2'], #using Red, Green & Blue bands for TCI.
      'min': 0,
      'max': 1,
      'gamma': 1
    }

    ## Other imagery processing operations go here 
    # NDVI
    def getNDVI(collection):
        return collection.normalizedDifference(['B8', 'B4'])

    # clipping to AOI
    ndvi = getNDVI(sat_imagery)

    # NDVI visual parameters:
    ndvi_params = {
    'min': 0,
    'max': 1,
    'palette': ['#ffffe5', '#f7fcb9', '#78c679', '#41ab5d', '#238443', '#005a32']
    }

    # Masking NDVI over the water & show only land
    ndvi = ndvi.updateMask(ndvi.gte(0))

    # ##### NDVI classification: 7 classes
    ndvi_classified = ee.Image(ndvi) \
    .where(ndvi.gte(0).And(ndvi.lt(0.15)), 1) \
    .where(ndvi.gte(0.15).And(ndvi.lt(0.25)), 2) \
    .where(ndvi.gte(0.25).And(ndvi.lt(0.35)), 3) \
    .where(ndvi.gte(0.35).And(ndvi.lt(0.45)), 4) \
    .where(ndvi.gte(0.45).And(ndvi.lt(0.65)), 5) \
    .where(ndvi.gte(0.65).And(ndvi.lt(0.75)), 6) \
    .where(ndvi.gte(0.75), 7) \

    # Classified NDVI visual parameters
    ndvi_classified_params = {
    'min': 1,
    'max': 7,
    'palette': ['#a50026', '#ed5e3d', '#f9f7ae', '#fec978', '#9ed569', '#229b51', '#006837']
    # each color corresponds to an NDVI class.
    }

    #### Satellite imagery Processing Section END

    #### Layers section START
    # add TCI layer to map
    m.add_ee_layer(tci_image, tci_params, 'True Color Image')
    # NDVI
    m.add_ee_layer(ndvi, ndvi_params, 'NDVI')
    # Classified NDVI
    m.add_ee_layer(ndvi_classified, ndvi_classified_params, 'NDVI - Classified')

    #### Layers section END

    #### Map result display
    # Folium Map Layer Control: we can see and interact with map layers
    folium.LayerControl(collapsed=False).add_to(m)
    
    # Display the map
    folium_static(m)

# Run the app
if __name__ == "__main__":
    main()
