import requests
from collections import defaultdict
import statistics
import urllib3
import pandas as pd
import os



# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Configuration
TOKEN = "eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiJ9.eyJhdWQiOiIzIiwianRpIjoiZTA4YjFjOTlkM2EwMjU4ZGM3NjczMmRhZTQyOTg0NTUwMWM3N2E2ZjZmMDMyYjNmOWQ3OWU0ZGU3MjZiMjY4OTY2ZDQ1YzBiN2E3YjU0YTEiLCJpYXQiOjE3NTUwNTQxODUuMTU3MTA1LCJuYmYiOjE3NTUwNTQxODUuMTU3MTA3MSwiZXhwIjoyNzAxNzM4OTg1LjE1MTM2MSwic3ViIjoiMTQ4NjQ3Iiwic2NvcGVzIjpbXX0.PPRm6OIb2Cbno4m7fcDhwjsjFQwm0fvFjmJT6kI-HKaInvqDONY3UkkqwsRTuRZoyx54PEDyn4eIt9pnYnyTaN99P3zsw3WMqGaSfdJ511aTq7G1VsfucR38rg2EyEN-40EzClSMyl0GeHe5W6265L00aJhqjyy07r5yGgXtn_CEsFdjz8UFEzWfpyn_eBPVcd1bTEA8McN5-sgvzmyhZ-6CIUz6VSH-e99JSiJE7uzFSw7zbCddbOkHznAlm8Ld5JVnVp7ucXnqMnQgcd-SgKtiMBx9A3iacpOfkGNlmIkief8p_i9Y0HTwKLd4BQvbTbpN93NENeY7mA3iGeUJyPh265hcfke9qzor6iKS7tF8ynevi7keJSUM_UlA3RQ9ZM6JapwBw2hQylY-XvWmUV2IeuAuI8Hn7LO6GW9hzwt7lICb9e3Ry0vZ7kwyVzTr5yf1m6bMDHDwbHVUq8f24gbvfcd8WTht4KmFrlnZuw6mTEcd4K3MaZHDFEv7jdFDWmYXhsfoeYkiYXgegRJTWYXWikYtaEhv0AGImhGvJ2tIARGIeD82ybXO_RRM1qPt2S0TIPQN4X9Lyka9vi5SRCHJK35yL4uu001DSVoUX_4bvdM24quybBNSCoJCUvf8yraJiS6N5P4tuCfyZ4by0m3jJLcVwm_uGec8zfdkbys"
EVENT_ID = "50374" # Main event ID to analyze

# Global variable to store event name
EVENT_NAME = None

# EPA Hyperparameters - TUNABLE PARAMETERS
INITIAL_EPA = 0.0      # Teams start at 25 EPA (shifts everyone up!)
INITIAL_RATING = 10.0   # Teams start at 10 rating (gets multiplied by S)
K_FACTOR = 8.0          # Learning rate for qualification matches (lower = less volatile)
K_FACTOR_PLAYOFF = 3.0  # Learning rate for playoff matches (lower than qual)
K_QUAL = 8.0            # Alternative name for K_FACTOR
K_PLAYOFF = 3.0         # Alternative name for K_FACTOR_PLAYOFF
MEAN_SCORE = 40.0       # Approximate mean score for VEX (adjust based on game)
SCORE_SD = 15.0         # Standard deviation of scores (adjust based on game)
S = 2.2                 # Scaling factor for converting ratings to EPA (MAIN TUNING KNOB)

# ==================== 0. GET EVENT INFORMATION ====================

def get_event_info():
    """Get event information including name"""
    global EVENT_NAME
    try:
        print(f"Getting event information for {EVENT_ID}...")
        response = requests.get(
            f"https://www.robotevents.com/api/v2/events/{EVENT_ID}",
            headers={"Authorization": f"Bearer {TOKEN}"},
            verify=False,
            timeout=10
        )
        response.raise_for_status()
        data = response.json()
        
        EVENT_NAME = data.get("name", f"Event_{EVENT_ID}")
        print(f"Event Name: {EVENT_NAME}")
        return EVENT_NAME
        
    except requests.exceptions.RequestException as e:
        print(f"API Error getting event info: {e}")
        EVENT_NAME = f"Event_{EVENT_ID}"
        return EVENT_NAME

def clean_sheet_name(name):
    """Clean event name to be valid Excel sheet name"""
    # Excel sheet names can't contain: \ / ? * [ ] :
    # and must be 31 characters or less
    invalid_chars = ['\\', '/', '?', '*', '[', ']', ':']
    clean_name = name
    for char in invalid_chars:
        clean_name = clean_name.replace(char, '-')
    
    # Truncate to 31 characters if too long
    if len(clean_name) > 31:
        clean_name = clean_name[:31]
    
    return clean_name

# ==================== 1. GET MATCH RESULTS FROM EVENT (2025-2026 SEASON ONLY) ====================

def get_event_matches_2025_2026():
    """Get all match results from the event, filtered for 2025-2026 season only"""
    try:
        all_matches = []
        page = 1
        per_page = 250  # Maximum allowed per page
        
        while True:
            print(f"Fetching page {page}...")
            response = requests.get(
                f"https://www.robotevents.com/api/v2/events/{EVENT_ID}/divisions/1/matches",
                headers={"Authorization": f"Bearer {TOKEN}"},
                params={"page": page, "per_page": per_page},
                verify=False,
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            
            page_matches = data["data"]
            if not page_matches:  # No more matches on this page
                break
                
            all_matches.extend(page_matches)
            
            # Check if we got less than per_page, meaning this is the last page
            if len(page_matches) < per_page:
                break
                
            page += 1
        
        print(f"Total matches found across all pages: {len(all_matches)}")
        
        # Now filter for valid matches
        filtered_matches = []
        season_matches = 0
        scored_matches = 0
        
        for match in all_matches:
            # Check season
            season_ok = False
            if "season" in match and match["season"]:
                season_name = match["season"].get("name", "")
                if "2025-2026" in season_name or "2025-26" in season_name:
                    season_ok = True
                    season_matches += 1
            else:
                # If no season info, assume it's current season
                season_ok = True
                season_matches += 1
            
            # Check if match is scored and has valid data
            if season_ok and len(match.get("alliances", [])) == 2:
                red_alliance = match["alliances"][0]
                blue_alliance = match["alliances"][1]
                
                red_score = red_alliance.get("score")
                blue_score = blue_alliance.get("score")
                
                if red_score is not None and blue_score is not None and isinstance(red_score, (int, float)) and isinstance(blue_score, (int, float)):
                    scored_matches += 1
                    filtered_matches.append({
                        "match_name": match["name"],
                        "red_teams": [team["team"]["name"] for team in red_alliance["teams"]],
                        "blue_teams": [team["team"]["name"] for team in blue_alliance["teams"]],
                        "red_score": red_score,
                        "blue_score": blue_score,
                        "is_playoff": match["round"] > 1,
                        "margin": red_score - blue_score
                    })
        
        print(f"Season matches: {season_matches}")
        print(f"Scored matches: {scored_matches}")
        print(f"Valid matches for EPA: {len(filtered_matches)}")
        
        return filtered_matches
    
    except requests.exceptions.RequestException as e:
        print(f"API Error: {e}")
        return []

# ==================== 2. GET RESULTS FROM A TEAM ====================

def get_team_results(team_name):
    """Get all match results for a specific team from the event"""
    all_matches = get_event_matches_2025_2026()
    team_matches = []
    
    for match in all_matches:
        if team_name in match["red_teams"] or team_name in match["blue_teams"]:
            team_alliance = "red" if team_name in match["red_teams"] else "blue"
            team_won = (team_alliance == "red" and match["red_score"] > match["blue_score"]) or \
                      (team_alliance == "blue" and match["blue_score"] > match["red_score"])
            
            match_copy = match.copy()
            match_copy["team_alliance"] = team_alliance
            match_copy["team_won"] = team_won
            team_matches.append(match_copy)
    
    return team_matches

# ==================== 3. GET EPA FROM 1 INDIVIDUAL TEAM ====================

def get_team_epa(team_name):
    """Calculate EPA rating for a single team"""
    all_matches = get_event_matches_2025_2026()
    
    if not all_matches:
        return 0
    
    # Initialize ratings for all teams
    R = defaultdict(lambda: INITIAL_RATING)
    
    # Calculate margins for standard deviation
    margins = [match["margin"] for match in all_matches]
    sigma_margin = statistics.stdev(margins) if len(margins) > 1 else 1
    
    # Process each match to calculate ratings
    for match in all_matches:
        R_red = sum(R[team] for team in match["red_teams"])
        R_blue = sum(R[team] for team in match["blue_teams"])
        
        deltaR = R_red - R_blue
        predicted_margin = S * deltaR
        actual_margin = match["margin"]
        
        norm_pred = predicted_margin / sigma_margin
        norm_actual = actual_margin / sigma_margin
        
        K = K_PLAYOFF if match["is_playoff"] else K_QUAL
        delta_alliance = K * (norm_actual - norm_pred)
        
        # Distribute rating changes
        for team in match["red_teams"]:
            R[team] += delta_alliance / len(match["red_teams"])
        for team in match["blue_teams"]:
            R[team] -= delta_alliance / len(match["blue_teams"])
    
    # Return EPA for the specific team
    return (R[team_name] * S) + INITIAL_EPA

# ==================== 4. GET EPA RANKINGS ====================

def get_epa_rankings():
    """Get EPA rankings for all teams in descending order"""
    all_matches = get_event_matches_2025_2026()
    
    if not all_matches:
        return []
    
    # Initialize ratings for all teams
    R = defaultdict(lambda: INITIAL_RATING)
    
    # Calculate margins for standard deviation
    margins = [match["margin"] for match in all_matches]
    sigma_margin = statistics.stdev(margins) if len(margins) > 1 else 1
    
    # Process each match to calculate ratings
    for match in all_matches:
        R_red = sum(R[team] for team in match["red_teams"])
        R_blue = sum(R[team] for team in match["blue_teams"])
        
        deltaR = R_red - R_blue
        predicted_margin = S * deltaR
        actual_margin = match["margin"]
        
        norm_pred = predicted_margin / sigma_margin
        norm_actual = actual_margin / sigma_margin
        
        K = K_PLAYOFF if match["is_playoff"] else K_QUAL
        delta_alliance = K * (norm_actual - norm_pred)
        
        # Distribute rating changes
        for team in match["red_teams"]:
            R[team] += delta_alliance / len(match["red_teams"])
        for team in match["blue_teams"]:
            R[team] -= delta_alliance / len(match["blue_teams"])
    
    # Convert to EPA points and sort
    epa_ratings = {team: (rating * S) + INITIAL_EPA for team, rating in R.items()}
    sorted_teams = sorted(epa_ratings.items(), key=lambda x: x[1], reverse=True)
    
    return sorted_teams

# ==================== MAIN - PRINT ALL EPA RANKINGS ====================

def export_to_excel(rankings):
    """Export EPA rankings to Excel file"""
    try:
        # Get event name if not already retrieved
        if EVENT_NAME is None:
            get_event_info()
        
        # FIXED: Correct path to your existing Excel file
        excel_path = r"C:\Users\nga28\OneDrive - Barker College\Desktop\Robotics\Statistics Calculator\V5RC_Statistics_Calculator\Pushback Statistics.xlsx"
        
        # Clean event name for Excel sheet naming
        sheet_name = clean_sheet_name(EVENT_NAME)
        
        # Create DataFrame from rankings
        df = pd.DataFrame(rankings, columns=['Team', 'EPA'])
        df['Rank'] = range(1, len(df) + 1)
        df = df[['Rank', 'Team', 'EPA']]  # Reorder columns
        
        # Check if file exists
        if os.path.exists(excel_path):
            # Check if sheet already exists (with better error handling)
            existing_sheets, error = check_existing_sheets(excel_path)
            
            if error:
                print(f"❌ {error}")
                print("💡 Please close the Excel file and run the script again")
                return
            
            if existing_sheets and sheet_name in existing_sheets:
                print(f"🔄 Sheet '{sheet_name}' already exists - updating data...")
                action = "updated"
            else:
                print(f"➕ Adding new sheet '{sheet_name}'...")
                action = "added"
            
            # Add/update the sheet
            with pd.ExcelWriter(excel_path, mode='a', engine='openpyxl', if_sheet_exists='replace') as writer:
                df.to_excel(writer, sheet_name=sheet_name, index=False)
            print(f"✅ Sheet '{sheet_name}' {action} in existing Excel file")
        else:
            # File doesn't exist - create new one
            df.to_excel(excel_path, sheet_name=sheet_name, index=False)
            print(f"✅ New Excel file created with sheet '{sheet_name}': {excel_path}")
            print("⚠️  Warning: Original file not found, created new file at specified location")
            
        print(f"📊 Exported {len(rankings)} teams to sheet '{sheet_name}'")
        
    except PermissionError:
        print("❌ Permission denied: Excel file is open in another program")
        print("💡 Please close the Excel file and run the script again")
        
        # Don't try fallback if it's a permission error
        return
        
    except Exception as e:
        print(f"❌ Error exporting to Excel: {e}")
        print("💡 Make sure the Excel file isn't open in another program")
        
        # Fallback: save to desktop with event name
        fallback_filename = f"EPA_Rankings_{clean_sheet_name(EVENT_NAME if EVENT_NAME else EVENT_ID)}.xlsx"
        desktop_path = rf"C:\Users\nga28\Desktop\{fallback_filename}"
        try:
            df.to_excel(desktop_path, sheet_name=sheet_name, index=False)
            print(f"💾 Fallback: Saved to {desktop_path}")
        except Exception as fallback_error:
            print(f"❌ Fallback also failed: {fallback_error}")

def check_existing_sheets(excel_path):
    """Safely check existing sheets in Excel file"""
    try:
        existing_sheets = pd.ExcelFile(excel_path).sheet_names
        return existing_sheets, None
    except PermissionError:
        return None, "File is currently open in another program (close Excel and try again)"
    except Exception as e:
        return None, f"Error reading file: {str(e)}"

def main():
    # Get event information first
    event_name = get_event_info()
    
    print(f"Analyzing event {EVENT_ID}: {event_name}")
    print(f"EPA Parameters: K_QUAL={K_QUAL}, K_PLAYOFF={K_PLAYOFF}, S={S}")
    
    # Check if this event has already been processed
    excel_path = r"C:\Users\nga28\OneDrive - Barker College\Desktop\Robotics\Statistics Calculator\V5RC_Statistics_Calculator\Pushback Statistics.xlsx"
    sheet_name = clean_sheet_name(event_name)
    
    if os.path.exists(excel_path):
        existing_sheets, error = check_existing_sheets(excel_path)
        
        if error:
            print(f"❌ {error}")
            print("💡 Please close the Excel file and run the script again")
            return
        
        if existing_sheets and sheet_name in existing_sheets:
            print(f"⚠️  Event '{event_name}' already processed (sheet exists)")
            user_input = input("Do you want to update the existing data? (y/n): ").lower().strip()
            if user_input != 'y':
                print("❌ Skipping event processing")
                return
    
    # Use function #4 to get and print all EPA rankings
    rankings = get_epa_rankings()
    
    if not rankings:
        print("No EPA rankings found")
        return
    
    # Print range statistics
    max_epa = max(epa for _, epa in rankings)
    min_epa = min(epa for _, epa in rankings)
    print(f"EPA Range: {max_epa:.1f} to {min_epa:.1f} (spread: {max_epa - min_epa:.1f})")
    
    print(f"\nEPA Rankings for Event {EVENT_ID} - {event_name}:")
    print("=" * 60)
    for i, (team, epa) in enumerate(rankings, 1):
        print(f"{i:2d}. {team}: {epa:.1f}")
    
    # Export to Excel
    export_to_excel(rankings)

if __name__ == "__main__":
    main()