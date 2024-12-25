from bs4 import BeautifulSoup
import pandas as pd
import requests
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
from prefect import task, flow
from pydantic import BaseModel
from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse, FileResponse
from io import BytesIO

from fastapi import APIRouter

router = APIRouter()



@task
def fetch_german_polls(plot: bool = False):
    # Define a dictionary of polling institutes and their respective URLs
    ingestion_date = datetime.now().strftime('%Y-%m-%d')

    institutes = {
        'Allensbach': 'https://www.wahlrecht.de/umfragen/allensbach.htm',
        'Forsa': 'https://www.wahlrecht.de/umfragen/forsa.htm',
        'Politbarometer': 'https://www.wahlrecht.de/umfragen/politbarometer.htm'
    }

    all_data = []


    # Iterate over each institute and its URL
    for institute, url in institutes.items():
        response = requests.get(url)
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Locate the main results table
        table = soup.find('table', class_='wilko')
        headers = [th.get_text(strip=True) for th in table.find('thead').find('tr').find_all('th')]
        
        # Determine the range of party columns
        end_index = headers.index('Sonstige') if 'Sonstige' in headers else len(headers) - 3
        date_col_index = 0
        party_columns = headers[2:end_index]
        
        # Extract rows from the table body
        rows = table.find('tbody').find_all('tr') if table.find('tbody') else table.find_all('tr')[1:]
        
        # Process each row to extract data
        for row in rows:
            cells = row.find_all(['td', 'th'])
            if not cells:
                continue
            
            date_str = cells[date_col_index].get_text(strip=True)
            
            try:
                date = datetime.strptime(date_str, '%d.%m.%Y')
            except ValueError:
                continue
            
            data_cells = cells[2:end_index]
            if len(data_cells) != len(party_columns):
                continue
            
            for party, cell in zip(party_columns, data_cells):
                val = cell.get_text(strip=True)
                val = None if val == '–' else float(val.replace('%', '').replace(',', '.')) if val else None
                
                all_data.append({
                    'date': date,
                    'institute': institute,
                    'party': party,
                    'percentage': val
                })

    # Create a DataFrame from the collected data
    df = pd.DataFrame(all_data)

    if plot:
        # Pivot the DataFrame to prepare for plotting
        pivot_df = df.groupby(['date', 'party'])['percentage'].mean().unstack('party').sort_index()
        smoothed_df = pivot_df.rolling(window=7, min_periods=1).mean()

        # Plot the smoothed data
        plt.figure(figsize=(12, 6))
        for party in smoothed_df.columns:
            plt.plot(smoothed_df.index, smoothed_df[party], label=party)
        plt.legend()
        plt.title("German Polls Over Time")
        plt.xlabel("Date")
        plt.ylabel("Percentage")
        plt.grid(True)

        # Save plot to a BytesIO object
        buf = BytesIO()
        plt.savefig(buf, format='png')
        buf.seek(0)
        plt.close()

        return buf

    df = df.replace([float('inf'), float('-inf')], None).fillna(0)
    
    # Convert datetime objects to strings
    df['date'] = df['date'].dt.strftime('%Y-%m-%d')

    return df

@router.get("/germany")
async def get_germany_polls(
        latest: bool = Query(False, description="Return only the latest poll block for each institute"),
        summarised: bool = Query(False, description="Collapsed polls and ordered by percentage")
    ):
    df = fetch_german_polls()
    
    # Ensure 'date' column is of datetime type
    df['date'] = pd.to_datetime(df['date'])
    
    if latest:
        # Get the latest date for each institute
        latest_dates = df.groupby('institute')['date'].max().reset_index()
        # Merge to filter the DataFrame to only include the latest block for each institute
        df = df.merge(latest_dates, on=['institute', 'date'])
    
    if summarised:
        # Filter data for the last two weeks
        two_weeks_ago = datetime.now() - timedelta(weeks=2)
        df = df[df['date'] >= two_weeks_ago]
        
        # Group by party and calculate the mean percentage
        df = df.groupby('party')['percentage'].mean().reset_index()
        
        # Sort by percentage in descending order
        df = df.sort_values(by='percentage', ascending=False)
    
    # Replace inf values with None and NaN values with a specific value (e.g., 0)
    df = df.replace([float('inf'), float('-inf')], None).fillna(0)
    
    return JSONResponse(content=df.to_dict(orient='records'))