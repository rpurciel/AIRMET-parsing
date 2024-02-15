import sys
import os
from pathlib import Path, PurePath
import math
import re

import pandas as pd

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

DEF_ANCILLARY_PATH_TO_VORS_RELATIVE_TO_SRC = "ancillary/vors.csv"

class Bounds():
    ''' A "Bounds" object = A
        collection of VORs for a
        single MET Info obj, along
        with the corresponding lat-
        lon pairs for each VOR. 

        Contains Iterables:
        - Lat/Lon Tuples
        - Raw VORs
    '''

    def __init__(self, vor_string):

        self.raw_string = vor_string
        self.vor_tuples = self._parse_vor_string(vor_string)

        self.latlon_points = []
        for vor in self.vor_tuples:
            dir_args = []
            if vor.find(" ") != -1:
                dir_vor = vor.split(" ")
                dist_carddir = dir_vor[0]
                vor = dir_vor[1]

                number_match = re.match(r"^\d*", dist_carddir)
                dist_nm = dist_carddir[:number_match.end()]
                card_dir = dist_carddir[number_match.end():]

                dir_args.append(dist_nm.strip())
                dir_args.append(card_dir.strip())

            vor_lat, vor_lon = self._vor_dir_to_lat_lon(vor)
            self.latlon_points += [(vor_lat, vor_lon)]

    def __iter__(self):
        self.num_points = len(self.latlon_points)
        self.iter_idx = 0
        return self

    def __next__(self):
        if self.iter_idx < self.num_points:
            this_tuple = self.latlon_points[self.iter_idx]
            self.iter_idx += 1
            return this_tuple
        else:
            raise StopIteration

    def __getitem__(self, idx):
        return self.latlon_points[idx]

    def __str__(self):
        return self.raw_string

    def _parse_vor_string(self, vor_string):
        '''
        Complex function to parse VORs from
        a string, and return a list of tuples
        comprised of (VOR ID, Dist. from VOR [if any]).

        3 parsing "schemes" are implemented.

        Scheme 1 parses VORs formatted like:
        FROM [DIR VOR|VOR] TO [DIR VOR|VOR] TO ...
        Typical in: Std. AIRMET format, SIGMET format

        Scheme 2 parses VORs formatted like:
        BOUNDED BY [DIR VOR|VOR]-[DIR VOR|VOR]-...
        Typical in: Other AIRMET products (outlooks,
        LLWS potential)

        Scheme 3 parses VORs formatted like:
        [A-Z] [DIR VOR|VOR]-[DIR VOR|VOR]-...
        Typical in: AIRMET complex FRZLVL,
        convective SIGMETs.

        Schemes 1 and 2 are checked for, and
        if both fail scheme 3 is used.

        '''

        initalvor_scheme1 = re.search(r"FROM(\s|\#)(((\d|[A-Z]){3,6}(\s|\#)([A-Z]){3})|([A-Z]){3}(?!-))", vor_string) #Matches inital VOR (FROM [...]) in typical AIRMET scheme
        vors_scheme1 = re.finditer(r"TO(\s|\#)(((\d|[A-Z]){3,6}(\s|\#)([A-Z]){3})|([A-Z]){3}(?!-))", vor_string) #Matches all other VORs (TO [...]) in typical AIRMET scheme
        
        initalvor_scheme2 = re.search(r"(BOUNDED BY)(\s|\#)(((\d|[A-Z]){3,6}(\s|\#)([A-Z]){3})|([A-Z]){3})", vor_string) #Matches inital VOR from alternate scheme (BOUNDED BY [...]-[...])
        vors_scheme2 = re.finditer(r"-(\#(\s)*)*(((\d|[A-Z]){3,6}(\s|\#)([A-Z]){3})|([A-Z]){3})", vor_string) #Matches all other VORs from alternate scheme (BOUNDED BY [...]-[...])
        
        vors_with_endpos = []
        start_pos_of_vors = 0
        end_pos_of_vors = 0   

        #VORS are in scheme 1 
        if initalvor_scheme1:
            # print("SCHEME 1")
            # print(initalvor_scheme1)
            vors_with_endpos.append((vor_string[initalvor_scheme1.start():initalvor_scheme1.end()], initalvor_scheme1.end()))
            start_pos_of_vors = initalvor_scheme1.start()
            end_pos_of_vors = 0       
                             
            for vor in vors_scheme1:
                # print(vor)
                vors_with_endpos.append((vor_string[vor.start():vor.end()], vor.end()))
                if vor.end() > end_pos_of_vors:
                    end_pos_of_vors = vor.end()
                         
            no_vor_text = vor_string[:start_pos_of_vors] + vor_string[end_pos_of_vors:]

        elif initalvor_scheme2:
            # print("SCHEME 2")
            # print(initalvor_scheme2)
            vors_with_endpos.append((vor_string[initalvor_scheme2.start():initalvor_scheme2.end()], initalvor_scheme2.end()))
            start_pos_of_vors = initalvor_scheme2.start()
            end_pos_of_vors = 0       
                             
            for vor in vors_scheme2:
                # print(vor)
                vors_with_endpos.append((vor_string[vor.start():vor.end()], vor.end()))
                if vor.end() > end_pos_of_vors:
                    end_pos_of_vors = vor.end()
            
        else:
            #TODO: Implement Scheme 3
            return []
            
        vor_tuples = []
        for vor_and_endpos in vors_with_endpos: #quality checks and sanitizing
            vor = vor_and_endpos[0]
            endpos = vor_and_endpos[1]
            
            vor = vor.replace("#", " ").replace("BOUNDED BY ", "").replace("-", "").replace("FROM ", "").replace("TO ", "")
            
            time_match = re.match(r"(\d{2}|\d{2}00)Z", vor) #matches if VOR includes a time. Can happen when product references a period a period (e.g. 12Z-15Z)
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
                            
            vor_tuples.append(vor)
            
        # if end_pos_of_vors == -999: #reset end position of VOR block if needed
        #     new_endpos = 0
        #     for vor_and_endpos in vors_with_endpos:
        #         endpos = vor_and_endpos[1]
        #         if endpos > new_endpos:
        #             new_endpos = endpos
        #     end_pos_of_vors = new_endpos
                         
        # no_vor_text = vor_string[:start_pos_of_vors] + vor_string[end_pos_of_vors:]

        return vor_tuples

    def _vor_dir_to_lat_lon(self, vor, *args):

        complex_vor_flag = False

        if args != ():
            args = args[0]
            distance_nm = int(args[0])
            cardinal = args[1]
            bearing_deg = DEF_CARDINAL_DIR_TO_DEG_DICT.get(cardinal)
            complex_vor_flag = True

        vor_path = PurePath.joinpath(Path.cwd(), DEF_ANCILLARY_PATH_TO_VORS_RELATIVE_TO_SRC)

        vors_master_list = pd.read_csv(vor_path, sep=",", na_values = ["0","M"], index_col=0)

        try:
            vor_data = vors_master_list.loc[vor]
        except:
            print(f"ERROR: VOR data not found for '{vor}'. Please add an issue on Github with more details.")

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

class Conditions():
    ''' A "Conditions" object = A
        collection of weather conditions
        or other type identifiers
        about the METInfo Object.
    '''

    translation_table = 
    
    def __init__(self, conds, desc_string):

        self.raw_conds = conds
        self.raw_desc = desc_string

        pass

class States():

    def __init__(self, state_string):

        self.raw_string = state_string
        self.states = self._parse_state_string(state_string)

    def __contains__(self, item):
        for state in self.states:
            if item == state:
                return True
        return False

    def __iter__(self):
        self.num_states = len(self.states)
        self.iter_idx = 0
        return self

    def __next__(self):
        if self.iter_idx < self.num_states:
            this_state = self.states[self.iter_idx]
            self.iter_idx += 1
            return this_state
        else:
            raise StopIteration

    def __str__(self):
        return self.raw_string

    def _parse_state_string(self, state_string):
        clean_str = state_string.replace("AND CSTL WTRS", "CSTL_WTRS")
        return clean_str.split(" ")


if __name__ == "__main__":

    vor_test_1 = "FROM 40ESE YDC TO 30NNE EPH TO 50S GEG TO 50NNE GEG TO 50SE REO TO 40SE LKV TO 40SSW FMG TO 40S OAL TO 30NNW CZQ TO 20SSW PYE TO 20WNW FOT TO 80W OED TO 40S TOU TO 20W TOU TO HUH TO 40ESE YDC"
    vor_test_2 = "BOUNDED BY TOU-EPH-DBS-CHE-SNY-GLD-50W LBL-30ESE TBE-20SSW TXO-40WNW CME-TBC-60N FMG-190WSW HQM-140W TOU-TOU"

    vor_obj_1 = Bounds(vor_test_1)

    print(vor_obj_1)

    for point in vor_obj_1:
        print(point)

    vor_obj_2 = Bounds(vor_test_2)

    state_test_1 = "ID MT WY NV UT CO AZ"
    state_test_2 = "ND SD NE KS MN IA MO WI LM LS MI LH IL IN KY OK TX AR TN LA MS AL AND CSTL WTRS"

    state_objs = [States(state_test_1), States(state_test_2)]
    states = ["AL", "AK", "AZ", "AR", "AS", "CA", "CO", "CT", "DE", "DC", "FL", "GA", "GU", "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "MP", "OH", "OK", "OR", "PA", "PR", "RI", "SC", "SD", "TN", "TX", "TT", "UT", "VT", "VA", "VI", "WA", "WV", "WI", "WY", "CSTL_WTRS"]

    for obj in state_objs:
        print("TESTING:", obj)
        for state in states:
            if state in obj:
                print(state, ": YES")
            else:
                print(state, ": NO")

        for state in obj:
            print(state)











