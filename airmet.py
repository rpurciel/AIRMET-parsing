###TODO: Smart logging for sub functions of download
###      Making everything into classes might make everything easier?

import requests
import sys
import os
import warnings
from pathlib import Path, PurePath
import math
import re
from datetime import datetime
import json

import pandas as pd
import simplekml

# sys.path.insert(0, "/Users/ryanpurciel/Development/wexlib/src")
# sys.path.insert(0, "/Users/rpurciel/Development/wexlib/src") #FOR TESTING ONLY!!!
# import wexlib.util.internal as internal

warnings.filterwarnings("ignore")

DEF_STATE_FILTER = False

DEF_CARDINAL_DIR_TO_DEG_DICT = {
    "N" : 0,
    "NNE" : 22.5,
    "NE" : 45,
    "ENE" : 67.5,
    "E" : 90,
    "ESE" : 112.5,
    "SE" : 135,
    "SSE" : 157.5,
    "S" : 180,
    "SSW" : 202.5,
    "SW" : 225,
    "WSW" : 247.5,
    "W" : 270,
    "WNW" : 292.5,
    "NW" : 315,
    "NNW" : 337.5,
}

DEF_AIRMET_TYPE_TO_COND_DICT = {
	"SIERRA" : "IFR",
	"TANGO" : "TURB",
	"ZULU" : "ICE"
}

DEF_ANCILLARY_PATH_TO_VORS_RELATIVE_TO_SRC = "ancillary/vors.csv"

def str_to_bool(string):
    if string in ['true', 'True', 'TRUE', 't', 'T', 'yes', 'Yes', 'YES', 'y', 'Y', True]:
        return True
    if string in ['false', 'False', 'FALSE', 'f', 'F', 'no', 'No', 'NO', 'n', 'N', False]:
        return False
    else:
        return False #fallback to false

def download(save_dir, year, month, day, **kwargs):

    start_time = datetime.now()

    if not os.path.exists(save_dir):
        os.makedirs(save_dir)

    if str_to_bool(kwargs.get("verbose")) == True:
        verbose = True
        print("INFO: VERBOSE mode turned ON")
    else:
        verbose = False

    if str_to_bool(kwargs.get("debug")) == True:
        debug = True
        verbose = True
        print("INFO: DEBUG mode turned ON")
    else:
        debug = False

    if debug:
        print("DEBUG: Kwargs passed:", kwargs)

    headers = {"Accept": "application/json"}
    date = f"{str(year).zfill(4)}-{str(month).zfill(2)}-{str(day).zfill(2)}"
    all_product_url = f"https://mesonet.agron.iastate.edu/api/1/nws/afos/list.json?cccc=kkci&date={date}"

    if verbose:
        print(f"SCRAPER: Scraping all products from URL {all_product_url}")

    try:
        all_product_request = requests.get(all_product_url, headers=headers)
        if verbose:
            print(f"SCRAPER: Success")
    except Exception as e:
        error_str = ("ERROR: ", e)

        if verbose:
            print("ERROR:", e)

        elapsed_time = datetime.now() - start_time
        return 0, elapsed_time.total_seconds(), error_str

    json_data = all_product_request.json()
    all_prods = []
    all_airmets_raw_text = []

    for prod in json_data["data"]:
        if debug:
            print(f"DEBUG: Selected product: \n {prod}")
        sel_pil = prod["pil"]
        if not sel_pil.startswith("WA"):
            if debug:
                print("DEBUG: Product not AIRMET, skipping...")
            pass
        else:
            sel_prod_id = prod["product_id"]
            airmet_url = f"https://mesonet.agron.iastate.edu/api/1/nwstext/{sel_prod_id}"
            if debug:
                print(f"DEBUG: Product is an AIRMET")
            if verbose:
                print(f"SCRAPER: Getting AIRMET with ID {sel_prod_id} from URL {airmet_url}")
            try:
                airmet_request = requests.get(airmet_url, headers=headers)
                if verbose:
                    print(f"SCRAPER: Success")
            except Exception as e:
                if verbose:
                    print("FATAL ERROR:", e)

                elapsed_time = datetime.now() - start_time
                return 0, elapsed_time.total_seconds(), e

            airmet_raw_text = airmet_request.text
            all_airmets_raw_text += [airmet_raw_text]
            if debug:
                print("DEBUG: Raw AIRMET: \n", airmet_raw_text)
            san_airmet = _sanitize_for_reading(airmet_raw_text)
            
            airmet_block = san_airmet[:san_airmet.rfind("=")]
            if debug:
                print("DEBUG: AIRMET block: \n", airmet_block)
            airmet_groups = airmet_block.split("+")
            groups_list = []
            num_groups = len(airmet_groups)
            group_idx = 1

            for group in airmet_groups:
                if verbose:
                    print(f"PARSING: Starting parsing airmet group {group_idx}/{num_groups}")
                if debug:
                    print("PARSING: Selected AIRMET group: \n", group)
                #group_raw_text = _reverse_sanitize_for_printing(group, kwargs)
                if group.find("*") != -1: #Header block
                    if debug:
                        print("PARSING: Group is a header block, parsing accordingly...")
                    header = group.replace("*", "")
                    header_dict = _header_to_dict(header)
                    
                    group_idx += 1
                    if verbose:
                        print("PARSING: Finished parsing airmet header")
                    if debug:
                        print(f"PARSING: Parsed header: {header_dict}")
                    
                else:
                    sigmet_series_match = re.search(r"\$(\w+|\s)+\$\#\.", group) #Remove any "SEE SIGMET XRAY SERIES" messages, they mess everything up
                    if sigmet_series_match:
                      group = group[sigmet_series_match.end():]

                    if debug:
                        print("PARSING: Parsing VORs from airmet...")
                    airmet_no_vor, vors = _pop_vors(group)
                    if debug:
                        print(f"PARSING: Parsed VORs: {vors}")

                    if debug:
                        print("PARSING: Parsing states from airmet...")
                    airmet_no_vor.replace("##", "$") #Able to use double pound from VOR block to mark end of states block
                    airmet_no_vor_no_state, states = _pop_states(airmet_no_vor)
                    if debug:
                        print(f"PARSING: Parsed states: {states}")

                    if debug:
                        print("PARSING: Parsing description from airmet...")
                    airmet_no_vsd, desc = _pop_description(airmet_no_vor_no_state)
                    if debug:
                        print(f"PARSING: Parsed description: {desc}")

                    if debug:
                        print("PARSING: Parsing qualifiers from airmet...")
                    quals = _pop_qualifiers(airmet_no_vsd)
                    if debug:
                        print(f"PARSING: Parsed qualifiers: {quals}")
                    
                    frz_present = False
                    for qual in quals:
                        if qual.find("FRZ") != -1:
                            frz_present = True

                    if frz_present:
                        if debug:
                            print("PARSING: Freezing level data found. Parsing not yet implemented.")
                        airmet_group = {"qualifiers" : quals, "error" : "Freezing level data parsing not yet implemented."}
                        groups_list.append(airmet_group)
                    else:
                        airmet_group = {
                            "qualifiers" : quals,
                            "vors": vors,
                            "states" : states,
                            "desc" : desc,
                        }

                        groups_list.append(airmet_group)
                        if verbose:
                            print("PARSING: Finished parsing airmet group")
                        group_idx += 1
                        
            main_dict = header_dict.copy()
            main_dict.update({"raw_text" : airmet_raw_text.replace('', '').replace('', ''), "subgroups" : groups_list})
            if verbose:
                print(f"PARSING: AIRMET parsing finished")
            if debug:
                print(f"PARSING: AIRMET data: \n{main_dict}")
            
            all_prods.append(main_dict)
            
    if verbose:
        print("PARSING: Parsing of ALL AIRMETs finished. Saving to file...")

    file_name = f"AllAIRMET_RawText_{date.replace('-', '')}.txt"
    dest_path = os.path.join(save_dir, file_name)

    file_object = open(dest_path, "w")
    for text in all_airmets_raw_text:
        file_object.write(text)
    file_object.close()

    file_name = f"AllAIRMETS_{date.replace('-', '')}.json"
    dest_path = os.path.join(save_dir, file_name)

    file_object = open(dest_path, "w")
    file_object.write(json.dumps(all_prods, indent=2))
    file_object.close()

    elapsed_time = datetime.now() - start_time
    return 1, elapsed_time.total_seconds(), dest_path

def plot_kmz(save_dir, sugroups, airmet_type, airmet_id, airmet_raw_text, valid_time, iss_time, **kwargs):

    start_time = datetime.now()

    if not os.path.exists(save_dir):
        os.makedirs(save_dir)

    if str_to_bool(kwargs.get("verbose")) == True:
        verbose = True
        print("INFO: VERBOSE mode turned ON")
    else:
        verbose = False

    if str_to_bool(kwargs.get("debug")) == True:
        debug = True
        verbose = True
        print("INFO: DEBUG mode turned ON")
    else:
        debug = False

    if debug:
        print("DEBUG: Kwargs passed:", kwargs)

    airmet_kml = simplekml.Kml()

    iss_time_str = iss_time.strftime("%Y-%m-%d %H:%M:%S UTC")
    valid_time_str = valid_time.strftime("%Y-%m-%d %H:%M:%S UTC")

    cond_str = DEF_AIRMET_TYPE_TO_COND_DICT.get(airmet_type)

    airmet_kml.document.name = f"{airmet_id} [{cond_str}]"
    airmet_kml.document.description = f"{iss_time_str} THRU {valid_time_str}\n{airmet_raw_text}"

    state_filter = []
    for arg, value in kwargs.items():
        if arg == 'filter_by_states':
            state_filter = value

    num_polygons = 0

    for group in subgroups:
        if verbose:
            print(f"PLOTTER: Iterating through following group:\n{group}")
        quals = group.get("qualifiers")
        airmet_flag = False
        llws_pot_flag = False

        if not quals:
            quals = []

        for qual in quals:
            #print(f"QUAL: {qual}")
            if (qual.find("AIRMET") != -1) or (qual.find("LLWS") != -1):
                if verbose:
                    print(f"PLOTTER: Group is an AIRMET, should be plotted.")
                airmet_flag = True
                airmet_title = f"AIRMET {airmet_type}"

                if qual.find("LLWS") != -1:
                    if verbose:
                        print(f"PLOTTER: Group is an LLWS Potential Group, should be plotted.")
                    llws_pot_flag = True
                    airmet_title = f"LLWS POTENTIAL"

            else:
                if verbose:
                    print(f"PLOTTER: Group is an outlook, freezing level, or something else. Skipping plotting...")

        if airmet_flag:
            if state_filter:
                if verbose:
                    print(f"!!! PLOTTER: State filtering turned ON\nPLOTTER: Plotting AIRMETS that only intersect the following states: {state_filter}")

                states = group.get("states")
                includes_state_flag = False

                if not states:
                    states = []

                for state in states:
                    if state in selected_states:
                        includes_state_flag = True

                if includes_state_flag:
                    if verbose:
                        print("PLOTTER: AIRMET includes a specified state. Plotting...")        
                    vors = group.get("vors")
                    desc = group.get("desc")
                    airmet_for = quals[0]
                    desc_text = "FOR " + airmet_for[7:] + "\n" + desc
                    if llws_pot_flag:
                        desc_text = "FOR LLWS POTENTIAL\n" + desc

                    airmet_kml, status = _add_poly_to_kml(airmet_kml, vors, airmet_type, airmet_title, desc_text)
                    num_polygons += status

                else:
                    if verbose:
                        print("PLOTTER: AIRMET does not include a specified state. Skipping...")
            else:
                if verbose:
                    print("PLOTTER: Plotting AIRMET...")
                states = group.get("states")
                vors = group.get("vors")
                desc = group.get("desc")
                airmet_for = quals[0]
                desc_text = "FOR " + airmet_for[7:] + "\n" + desc
                if llws_pot_flag:
                    desc_text = "FOR LLWS POTENTIAL\n" + desc

                airmet_kml, status = _add_poly_to_kml(airmet_kml, vors, airmet_type, airmet_title, desc_text)
                num_polygons += status

    if num_polygons == 0:
        error_str = "NoPolygons"

        elapsed_time = datetime.now() - start_time
        return 0, elapsed_time.total_seconds(), error_str

    else:
        iss_time_str = iss_time.strftime("%Y%m%d_%H%M%S")
        valid_time_str = valid_time.strftime("%Y%m%d_%H%M%S")
        airmet_id_for_file = airmet_id.replace(" ", "")

        file_name = f"{airmet_id_for_file}_{cond_str}_iss{iss_time_str}_valid{valid_time_str}"

        dest_path = os.path.join(save_dir, file_name + ".kmz")

        airmet_kml.savekmz(dest_path)

        elapsed_time = datetime.now() - start_time
        return 1, elapsed_time.total_seconds(), dest_path
    
def _add_poly_to_kml(kml, list_of_vors, airmet_type, airmet_title, desc, **kwargs):

    if str_to_bool(kwargs.get("verbose")) == True:
        verbose = True
        print("INFO: VERBOSE mode turned ON")
    else:
        verbose = False

    if str_to_bool(kwargs.get("debug")) == True:
        debug = True
        verbose = True
        print("INFO: DEBUG mode turned ON")
    else:
        debug = False

    if debug:
        print("DEBUG: Kwargs passed:", kwargs)

    airmet_points = []

    for vor in list_of_vors:
        if debug:
            print(f"DEBUG: Selected vor {vor}")
        dir_args = []
        if vor.find(" ") != -1:
            if debug:
                print(f"DEBUG: Combination VOR/DIR, splitting...")
            dir_vor = vor.split(" ")
            dist_carddir = dir_vor[0]
            vor = dir_vor[1]

            number_match = re.match(r"^\d*", dist_carddir)
            dist_nm = dist_carddir[:number_match.end()]
            card_dir = dist_carddir[number_match.end():]

            if debug:
                print(f"DEBUG: VOR distance: {dist_nm}\nDEBUG: VOR cardinal direction: {card_dir}")

            dir_args.append(dist_nm.strip())
            dir_args.append(card_dir.strip())

        point_lat, point_lon = _vor_dir_to_lat_lon(vor, dir_args)

        if debug:
        	print(f"DEBUG: Selected point: ({point_lat}, {point_lon})")

        airmet_points.append((point_lon, point_lat))

    #airmet_points = airmet_points[:-1]

    if debug:
    	print(f"DEBUG: AIRMET points:")
    	print(airmet_points)

    if airmet_type == "SIERRA":
        polygon_line_color = simplekml.Color.violet
        polygon_line_width = 5
        polygon_color = simplekml.Color.changealphaint(60, simplekml.Color.violet)
    elif airmet_type == "ZULU":
        polygon_line_color = simplekml.Color.cyan
        polygon_line_width = 5
        polygon_color = simplekml.Color.changealphaint(60, simplekml.Color.cyan)
    elif airmet_type == "TANGO":
        polygon_line_color = simplekml.Color.coral
        polygon_line_width = 5
        polygon_color = simplekml.Color.changealphaint(60, simplekml.Color.coral)
    else:
        polygon_line_color = simplekml.Color.red
        polygon_line_width = 5
        polygon_color = simplekml.Color.changealphaint(60, simplekml.Color.red)

    airmet_poly = kml.newpolygon(name=airmet_title,
                                 description=desc,
                                 outerboundaryis=airmet_points,)

    airmet_poly.style.linestyle.color = polygon_line_color
    airmet_poly.style.linestyle.width = polygon_line_width
    airmet_poly.style.polystyle.color = polygon_color

    return kml, 1

def _vor_dir_to_lat_lon(vor, *args):

    complex_vor_flag = False

    if args != ([],):
        args = args[0]
        distance_nm = int(args[0])
        cardinal = args[1]
        bearing_deg = DEF_CARDINAL_DIR_TO_DEG_DICT.get(cardinal)
        complex_vor_flag = True


    vor_path = PurePath.joinpath(Path.cwd().parent, DEF_ANCILLARY_PATH_TO_VORS_RELATIVE_TO_SRC)

    vors_master_list = pd.read_csv(vor_path, sep=",", na_values = ["0","M"], index_col=0)

    try:
        vor_data = vors_master_list.loc[vor]
    except:
        print("ERROR: VOR data not found. Please add an issue on Github with details of this issue.")

    #print(vor_data)
    vor_lat = vor_data.lat
    vor_lon = vor_data.lon
    #print(f"LAT: {vor_lat}\nLON: {vor_lon}")

    if complex_vor_flag:

        eq_rad_km = 6378.137
        pol_rad_km = 6356.752

        bearing_rad = math.radians(bearing_deg)
        distance_km = 1.852 * distance_nm

        vor_lat_rad = math.radians(vor_lat)
        vor_lon_rad = math.radians(vor_lon)

        #Copied from earlier code
        #Sorry reader

        #Radius of earth at latitude
        vor_lat_earth_radius = (((((eq_rad_km**2)*math.cos(vor_lat_rad))**2)
                              +(((pol_rad_km**2)*math.sin(vor_lat_rad))**2))
                              /((eq_rad_km*math.cos(vor_lat_rad))**2
                              +(pol_rad_km*math.sin(vor_lat_rad))**2))**0.5

        #Latitude of airmet point in radians
        airmet_pt_lat_rad = math.asin(math.sin(vor_lat_rad)*math.cos(distance_km/vor_lat_earth_radius) +
                             math.cos(vor_lat_rad)*math.sin(distance_km/vor_lat_earth_radius)*math.cos(bearing_rad))

        #Longitude of airmet point in radians
        airmet_pt_lon_rad = vor_lon_rad + math.atan2(math.sin(bearing_rad)*math.sin(distance_km/vor_lat_earth_radius)*math.cos(vor_lat_rad),
                             math.cos(distance_km/vor_lat_earth_radius)-math.sin(vor_lat_rad)*math.sin(airmet_pt_lat_rad))

        airmet_pt_lat = math.degrees(airmet_pt_lat_rad)
        airmet_pt_lon = math.degrees(airmet_pt_lon_rad)

    else:

        airmet_pt_lat = vor_lat
        airmet_pt_lon = vor_lon

    return airmet_pt_lat, airmet_pt_lon

def _sanitize_for_reading(raw_text, **kwargs):
    '''Internal function to take a native-format AIRMET, and sanitize it for 
       machine parsing. Returns a sanitized string
    '''

    '''
    The function below does 4 things.
    1) Replaces "...." with "=", in order to delineate the end of the AIRMET
    2) Replaces "..." with "$", in order to delineate between the type of airmet 
            (e.g. AIRMET IFR) and the beginning of the states block
    3) Replaces unicode character 0x01 with "+*". This accomplishes two things:
            The "+" marks the beginning and end of a block (and in this case marks the beginning
            of the header)
            The "*" marks the beginning and end of the header block specifically.
    4) Replaces unicode character 0x1e with "&". This delineates the beinning of the header 
            information, seperating it from the automated information
    '''
    san_text = raw_text.replace("....", "=").replace("...", "$").replace("", "+*").replace("", "&")

    '''
    The function below replaces all two periods, seperated by a newline, with a period and "+".
    This delineates between different "groups" in the airmet.
    '''
    san_text = re.sub("\.\n\.", ".+", san_text)

    # The function below delineates the end of the header block with "*+".
    san_text = re.sub("00\n\.\n", "00*+", san_text)

    # The function below replaces all newlines with "#", for easier parsing
    san_text = san_text.replace("\n", "#")

    '''
    What's returned should follow the following structure:

    {AUTO_INFO}+*{HEADER}*
    +{AIRMET_TYPE}${STATES}#{VORS}#{DESC}+ 
    (...)
    =
    
    which is much more machine-parsable than before
    '''
    return san_text

def _pop_vors(text, **kwargs):
    initalvor_scheme1 = re.search(r"FROM(\s|\#)(((\d|[A-Z]){3,6}(\s|\#)([A-Z]){3})|([A-Z]){3}(?!-))", text) #Matches inital VOR (FROM [...]) in typical AIRMET scheme
    vors_scheme1 = re.finditer(r"TO(\s|\#)(((\d|[A-Z]){3,6}(\s|\#)([A-Z]){3})|([A-Z]){3}(?!-))", text) #Matches all other VORs (TO [...]) in typical AIRMET scheme
    
    initalvor_scheme2 = re.search(r"(BOUNDED BY)(\s|\#)(((\d|[A-Z]){3,6}(\s|\#)([A-Z]){3})|([A-Z]){3})", text) #Matches inital VOR from alternate scheme (BOUNDED BY [...]-[...])
    vors_scheme2 = re.finditer(r"-(\#(\s)*)*(((\d|[A-Z]){3,6}(\s|\#)([A-Z]){3})|([A-Z]){3})", text) #Matches all other VORs from alternate scheme (BOUNDED BY [...]-[...])
    
    vors_with_endpos = []
    start_pos_of_vors = 0
    end_pos_of_vors = 0    
    if initalvor_scheme1:
        # print("SCHEME 1")
        # print(initalvor_scheme1)
        vors_with_endpos.append((text[initalvor_scheme1.start():initalvor_scheme1.end()], initalvor_scheme1.end()))
        start_pos_of_vors = initalvor_scheme1.start()
        end_pos_of_vors = 0       
                         
        for vor in vors_scheme1:
            # print(vor)
            vors_with_endpos.append((text[vor.start():vor.end()], vor.end()))
            if vor.end() > end_pos_of_vors:
                end_pos_of_vors = vor.end()
                     
        no_vor_text = text[:start_pos_of_vors] + text[end_pos_of_vors:]
    elif initalvor_scheme2:
        # print("SCHEME 2")
        # print(initalvor_scheme2)
        vors_with_endpos.append((text[initalvor_scheme2.start():initalvor_scheme2.end()], initalvor_scheme2.end()))
        start_pos_of_vors = initalvor_scheme2.start()
        end_pos_of_vors = 0       
                         
        for vor in vors_scheme2:
            # print(vor)
            vors_with_endpos.append((text[vor.start():vor.end()], vor.end()))
            if vor.end() > end_pos_of_vors:
                end_pos_of_vors = vor.end()
        
    else:
        return text, []
        
    final_vors = []
    for vor_and_endpos in vors_with_endpos: #quality checks and sanitizing
        vor = vor_and_endpos[0]
        endpos = vor_and_endpos[1]
        
        vor = vor.replace("#", " ").replace("BOUNDED BY ", "").replace("-", "").replace("FROM ", "").replace("TO ", "")
        
        time_match = re.match(r"(\d{2}|\d{2}00)Z", vor) #matches if VOR includes a time. Can happen when referencing a period (e.g. 12Z-15Z)
        level_match = re.match(r"\d+(?!\w)", vor) #matches if VOR is just a number. Can sometimes happen if description references a level (e.g. SFC-100 [FL])
        caught_desc_match = re.match(r"(?<!\d)[A-Z]{3}\s[A-Z]+", vor) #matches if the VOR caught some of the description (e.g. parsed "YYZ MTNS OBSC" as "[YYZ MTN]S OBSC")
        
        #quality checks
        if len(vor) > 10 or len(vor) < 3 or time_match or level_match:
            if endpos == end_pos_of_vors:
                end_pos_of_vors = -999 #flagged for correction    
            continue
        
        if caught_desc_match:
            vor = vor.split(" ")[0] #save only first half of vor
            end_pos_of_vors = end_pos_of_vors - 4
                           
        vor = vor.lstrip().rstrip()
        # if vor.find(" ") != -1:
        #     vor = tuple(vor.split(" "))
                        
        final_vors.append(vor)
        
    if end_pos_of_vors == -999: #reset end position of VOR block if needed
        new_endpos = 0
        for vor_and_endpos in vors_with_endpos:
            endpos = vor_and_endpos[1]
            if endpos > new_endpos:
                new_endpos = endpos
        end_pos_of_vors = new_endpos
                     
    no_vor_text = text[:start_pos_of_vors] + text[end_pos_of_vors:]
    return no_vor_text, final_vors

def _pop_states(text, **kwargs):

    text = text.replace("##", "$") #Able to use double pound from VOR block to mark end of states block
    #print("POST", text)
    # print(text)
    
    start_of_block = text.find("$")
    end_of_block = text.rfind("$")
    if start_of_block == end_of_block:
        return text, []
    
    states_text = text[start_of_block+1:end_of_block]
    
    caught_airmet_match = re.match(r"^([A-Z]{3,}(\s*))+", states_text) #Matches if states block includes some of AIRMET description and not just state abbrs
    if caught_airmet_match:
        states_text = text[start_of_block+caught_airmet_match.end():end_of_block]
        
    states_text = states_text.replace("#", " ").lstrip()
        
    print(states_text)

    trailer_waters_match = states_text.find("WTRS$UPDT") #Found a case where "AND CSTL WTRS$UPDT" was included. This will get rid of that.
    if trailer_waters_match != -1:
        states_text = states_text[:trailer_waters_match+4]
    
    trailer_match = states_text.find("$UPDT") #Found a case where "$UPDT" was included at the end. This will get rid of that
    if trailer_match != -1:
        states_text = states_text[:trailer_match]
        
    states_only_match = re.match(r"([A-Z]{2}\s)*[A-Z]{2}$", states_text) #Matches only if states block is only state abbrs (e.g. [CA NV OR ...])
    #coastal_waters_match = re.match(r"((AND\s)*CSTL\sWTRS)", states_text) #Matches only if states block includes "and coastal waters"
    coastal_waters_match = states_text.find("CSTL")
    if coastal_waters_match == -1:
        coastal_waters_match = False
    else:
        coastal_waters_match = True
        
    
    # #print("TRAILER:", trailer_match)


    print(states_text)
    # print("STATES:", bool(states_only_match), states_only_match)
    # print("WATERS:", bool(coastal_waters_match), coastal_waters_match)
    if states_only_match:
        # print("YES")
        states = states_text.split(" ")
        no_state_text = text[:start_of_block] + text[end_of_block:]
    elif coastal_waters_match: #If states doesnt match but coastal waters does assume its a block of states since coastal waters would only be with locations anyway
        # print("NO BUT WATERS")
        print(states_text)
        states_text = states_text.replace("CSTL#WTRS", "CSTL_WTRS").replace("CSTL WTRS", "CSTL_WTRS").replace("AND CSTL_WTRS", "CSTL_WTRS")
        states = states_text.split(" ")
        states[states.index("CSTL_WTRS")] = "CSTL WTRS"
        no_state_text = text[:start_of_block] + text[end_of_block:]
    else:
        # print("NO")
        no_state_text = text
        states = []
    
    return no_state_text, states

def _pop_description(text, **kwargs):
    
    start_pos = text.rfind("$")
    
    desc = text[start_pos+1:].replace("#", " ")
    
    no_desc_text = text[:start_pos]
    
    return no_desc_text, desc

def _pop_qualifiers(text):
    
    if not text:
        return []
    
    if text[0] == "#" or text[0] == " ":
        text = text[1:]
        
    qualifiers = text.split("#")

    return qualifiers

def _header_to_dict(header, **kwargs):
    
    main_block_match = re.search(r"\#([A-Z]|\d){4}\s.+", header)
    
    header = header[main_block_match.start():]
    amended = False
    if header.find("AMD") != -1:
        header = header.replace(" AMD", "")
        amended = True
    
    airmet_id_match = re.search(r"^\#([A-Z]|\d){4}\s", header)
    airmet_airport_match = re.search(r"\#&([A-Z]|\d){4}\s", header)
    airmet_iss_time_match = re.search(r"\d{6}\#", header)
    airmet_type_match = re.search(r"\#AIRMET\s\w+", header)
    airmet_conds_match = re.search(r"FOR\s(\w|\s)+VALID", header)
    airmet_valid_time_match = re.search(r"VALID\sUNTIL\s\d{6}", header)
    
    airmet_id = header[airmet_id_match.start():airmet_id_match.end()].replace("#", "").strip()
    try:
        airmet_airport = header[airmet_airport_match.start():airmet_airport_match.end()].replace("#&", "").strip()
    except:
        airmet_airport = ''
    airmet_iss_time = header[airmet_iss_time_match.start():airmet_iss_time_match.end()].replace("#", "").strip()
    airmet_type = header[airmet_type_match.start():airmet_type_match.end()].replace("#AIRMET ", "").strip()
    airmet_valid_time = header[airmet_valid_time_match.start():airmet_valid_time_match.end()].replace("VALID UNTIL ", "").strip()
    
    if amended:
        airmet_id = airmet_id + " AMD"
    
    airmet_conds_str = header[airmet_conds_match.start():airmet_conds_match.end()].replace("FOR ", "").replace(" VALID", "")
    airmet_conds_str = airmet_conds_str.replace("STG WNDS", "STG_WNDS").replace("MTN OBSCN", "MTN_OBSCN").replace("STG SFC WNDS", "STD_SFC_WNDS").replace("AND ", "")
    airmet_conds = airmet_conds_str.split(" ")
    
    iss_day = int(airmet_iss_time[:2])
    iss_hour = int(airmet_iss_time[2:4])
    iss_minute = int(airmet_iss_time[4:6])
    
    valid_day = int(airmet_valid_time[:2])
    valid_hour = int(airmet_valid_time[2:4])
    valid_minute = int(airmet_valid_time[4:6])
    
    header_dict = {
        "airmet_id" : airmet_id,
        "iss_airport" : airmet_airport,
        "iss_year" : year,
        "iss_month" : month,
        "iss_day" : iss_day,
        "iss_hour" : iss_hour,
        "iss_minute" : iss_minute,
        "iss_time_str" : airmet_iss_time,
        "valid_year" : year,
        "valid_month" : month,
        "valid_day" : valid_day,
        "valid_hour" : valid_hour,
        "valid_minute" : valid_minute,
        "valid_time_str" : airmet_valid_time,
        "airmet_type" : airmet_type,
        "conditions" : airmet_conds,
    }
    
    return header_dict
    
if __name__ == "__main__":

    save_dir = "/Users/rpurciel/Documents/Solis v RAPCO/AIRMETS"

    year = 2020

    month = 3

    day = 13

    print("starting download")

    _, _, fpath = download(save_dir, year, month, day, verbose=True, debug=True)


    print("done")

    #selected_states = ["TN", "AL", "GA", "SC", "NC"]

    selected_states = ["WA"]

    with open(fpath) as file:
        data = file.read()

    #print(data)
    main_list = json.loads(data)

    save_dir = "/Users/rpurciel/Documents/Solis v RAPCO/AIRMETS"

    # test_airmet = [{"airmet_id": "WA4Z", "iss_airport": "DFWZ", "iss_time": "102045", "airmet_type": "ZULU", "valid_time": "110300", "conditions": ["ICE", "FRZLVL"], "subgroups": [{"qualifiers": ["AIRMET ICE"], "vors": ["30ENE ASP", "40S ECK", "FWA", "CVG", "HNN", "50S HNN", "50ENE DYR", "20WNW STL", "30SSE BAE", "30ENE ASP"], "states": ["TN", "MO", "WI", "LM", "MI", "IL", "IN", "KY"], "desc": "MOD ICE BTN FRZLVL AND FL220. FRZLVL 080-120. CONDS CONTG BYD 03Z THRU 09Z."}]}]
    airmets = len(main_list)
    index = 1

    for airmet in main_list:
        print(f"Plotting airmet {index} of {airmets}", end="\r")
        airmet_id = airmet.get("airmet_id")
        airmet_type = airmet.get("airmet_type")
        iss_time = datetime(airmet.get("iss_year"), airmet.get("iss_month"), airmet.get("iss_day"), airmet.get("iss_hour"), airmet.get("iss_minute"))
        valid_time = datetime(airmet.get("valid_year"), airmet.get("valid_month"), airmet.get("valid_day"), airmet.get("valid_hour"), airmet.get("valid_minute"))
        airmet_raw_text = airmet.get("raw_text")

        iss_str = "ISSUED " + iss_time.strftime("%Y-%m-%d %H:%M:%S")
        valid_str = "VALID UNTIL " + valid_time.strftime("%Y-%m-%d %H:%M:%S") 

        #print(airmet_id, airmet_type, cond_str)

        subgroups = airmet.get("subgroups")
        if not subgroups:
            subgroups = []

        _, _, _, = plot_kmz(save_dir, subgroups, airmet_type, airmet_id, airmet_raw_text, valid_time, iss_time, debug=True)
        index += 1


    






