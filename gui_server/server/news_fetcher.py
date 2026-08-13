"""
News Fetcher Module
Fetches high-impact economic news from ForexFactory
"""

import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import logging
import threading

logger = logging.getLogger(__name__)


class NewsFetcher:
    """Fetches and caches economic news data from ForexFactory"""

    def __init__(self):
        self.cache = []
        self.last_fetch = None
        self.cache_duration = timedelta(hours=4)  # Refresh every 4 hours (reduced from 1 hour to prevent rate limiting)
        self.base_url = "https://www.forexfactory.com/calendar"
        self._lock = threading.Lock()
        self._fetching = False

    def get_high_impact_news(self, hours_ahead: int = 4, hours_behind: int = 1) -> List[Dict]:
        """
        Get high-impact news events within time window
        Returns cached data immediately if available, triggers background refresh if expired.

        Args:
            hours_ahead: How many hours ahead to check (default: 4)
            hours_behind: How many hours behind to check (default: 1)

        Returns:
            List of news events with impact, time, currency, event name
        """
        # If cache is invalid but we have old data, return old data while fetching in background to avoid blocking
        if not self._is_cache_valid():
            if not self._fetching:
                logger.info("Triggering background fetch for ForexFactory news...")
                threading.Thread(target=self._background_fetch, daemon=True).start()
            
            # If we literally have no data yet at startup, we unfortunately must wait or return empty.
            # To minimize latency, we'll return empty if this is initial startup, so the first tick isn't slow.
            if not self.cache:
                logger.warning("No news cache available on first startup. Skipping news this tick to maintain extreme low latency.")
                return []
                
        logger.info("Using cached news data")
        return self._filter_news_by_time(self.cache, hours_ahead, hours_behind)

    def _background_fetch(self):
        """Perform the HTTP fetch in a background thread"""
        with self._lock:
            if self._fetching:
                return
            self._fetching = True
            
        try:
            news_data = self._fetch_forexfactory_news()
            if news_data is not None:
                self.cache = news_data
                self.last_fetch = datetime.now()
        except Exception as e:
            logger.error(f"Background fetch error: {e}")
        finally:
            self._fetching = False

    def _is_cache_valid(self) -> bool:
        """Check if cached data is still valid"""
        if not self.last_fetch or not self.cache:
            return False
        return datetime.now() - self.last_fetch < self.cache_duration
    
    def _fetch_forexfactory_news(self) -> List[Dict]:
        """Scrape ForexFactory calendar for high-impact events"""
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        try:
            response = requests.get(self.base_url, headers=headers, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            events = []
            calendar_rows = soup.find_all('tr', class_='calendar__row')
            
            current_date = None
            
            for row in calendar_rows:
                # Check if this row contains a date
                date_cell = row.find('td', class_='calendar__date')
                if date_cell and date_cell.text.strip():
                    # Parse the date
                    date_str = date_cell.text.strip()
                    try:
                        current_date = datetime.strptime(date_str, "%a%b %d").replace(year=datetime.now().year)
                    except:
                        pass
                
                # Extract impact level
                impact_span = row.find('td', class_='calendar__impact')
                if not impact_span:
                    continue
                    
                impact_icons = impact_span.find_all('span', class_='calendar__impact-icon--screen')
                impact_level = len([icon for icon in impact_icons if 'calendar__impact-icon--high' in icon.get('class', [])])
                
                # Only get high-impact events (3 red icons)
                if impact_level < 1:  # At least one high impact icon
                    continue
                
                # Extract time
                time_td = row.find('td', class_='calendar__time')
                time_str = time_td.text.strip() if time_td else ""
                
                # Extract currency
                currency_td = row.find('td', class_='calendar__currency')
                currency = currency_td.text.strip() if currency_td else ""
                
                # Extract event name
                event_td = row.find('span', class_='calendar__event-title')
                event_name = event_td.text.strip() if event_td else ""
                
                # Skip if no event name
                if not event_name:
                    continue
                
                # Parse time
                event_time = self._parse_event_time(time_str, current_date)
                
                if event_time:
                    events.append({
                        'time': event_time,
                        'currency': currency,
                        'event': event_name,
                        'impact': 'HIGH'
                    })
            
            logger.info(f"Fetched {len(events)} high-impact news events from ForexFactory")
            return events
            
        except requests.RequestException as e:
            logger.error(f"Network error scraping ForexFactory: {e}")
            return []
        except Exception as e:
            logger.error(f"Error parsing ForexFactory data: {e}")
            return []
    
    def _parse_event_time(self, time_str: str, event_date: Optional[datetime]) -> Optional[datetime]:
        """Parse event time string to datetime"""
        try:
            # Handle special cases
            if not time_str or time_str.lower() in ["all day", "tentative", "day"]:
                return None
            
            # Remove any extra whitespace
            time_str = time_str.strip()
            
            # Parse time (format: "9:30am" or "2:00pm")
            if event_date:
                base_date = event_date.date()
            else:
                base_date = datetime.now().date()
            
            # Try parsing with AM/PM
            try:
                time_obj = datetime.strptime(time_str, "%I:%M%p").time()
            except:
                try:
                    time_obj = datetime.strptime(time_str, "%H:%M").time()
                except:
                    return None
            
            return datetime.combine(base_date, time_obj)
            
        except Exception as e:
            logger.debug(f"Could not parse time '{time_str}': {e}")
            return None
    
    def _filter_news_by_time(self, news_data: List[Dict], hours_ahead: int, hours_behind: int) -> List[Dict]:
        """Filter news events within time window"""
        now = datetime.now()
        start_time = now - timedelta(hours=hours_behind)
        end_time = now + timedelta(hours=hours_ahead)
        
        filtered = []
        for event in news_data:
            if event['time'] and start_time <= event['time'] <= end_time:
                filtered.append(event)
        
        # Sort by time
        filtered.sort(key=lambda x: x['time'])
        
        return filtered
    
    def format_news_for_llm(self, news_events: List[Dict]) -> str:
        """Format news events for LLM prompt"""
        if not news_events:
            return "=== HIGH-IMPACT NEWS EVENTS ===\nNo high-impact news events in the next 4 hours."
        
        news_text = "=== HIGH-IMPACT NEWS EVENTS ===\n"
        
        for event in news_events:
            time_diff = (event['time'] - datetime.now()).total_seconds() / 60  # minutes
            
            if time_diff < -60:
                # More than 1 hour ago
                hours_ago = abs(int(time_diff / 60))
                time_str = f"{hours_ago} hour{'s' if hours_ago > 1 else ''} ago"
            elif time_diff < 0:
                # Less than 1 hour ago
                time_str = f"{abs(int(time_diff))} minutes ago"
            elif time_diff < 60:
                # Less than 1 hour ahead
                time_str = f"in {int(time_diff)} minutes"
            else:
                # More than 1 hour ahead
                hours_ahead = int(time_diff / 60)
                time_str = f"in {hours_ahead} hour{'s' if hours_ahead > 1 else ''}"
            
            news_text += f"- {event['currency']} | {event['event']} | {time_str}\n"
        
        return news_text
    
    def get_news_impact_on_pair(self, symbol: str, news_events: List[Dict]) -> str:
        """
        Determine if news affects the trading pair
        
        Args:
            symbol: Trading pair (e.g., "XAUUSD", "EURUSD")
            news_events: List of news events
            
        Returns:
            Impact level: "CRITICAL", "HIGH", "MODERATE", "LOW"
        """
        if not news_events:
            return "LOW"
        
        # Extract currencies from symbol
        # XAUUSD -> XAU (Gold) and USD
        # EURUSD -> EUR and USD
        symbol_upper = symbol.upper()
        
        # Map common symbols to currencies
        currency_map = {
            'XAU': 'USD',  # Gold primarily affected by USD
            'XAG': 'USD',  # Silver primarily affected by USD
            'EUR': 'EUR',
            'GBP': 'GBP',
            'JPY': 'JPY',
            'CHF': 'CHF',
            'AUD': 'AUD',
            'NZD': 'NZD',
            'CAD': 'CAD',
            'USD': 'USD'
        }
        
        # Find currencies in symbol
        affected_currencies = []
        for curr_code in currency_map.keys():
            if curr_code in symbol_upper:
                affected_currencies.append(curr_code)
        
        # Check if any news affects these currencies
        now = datetime.now()
        critical_window = timedelta(minutes=30)  # 30 minutes before/after
        
        for event in news_events:
            event_currency = event['currency'].upper()
            
            # Check if event currency matches symbol currencies
            if event_currency in affected_currencies or event_currency == 'USD':
                time_to_event = event['time'] - now
                
                # Critical if within 30 minutes
                if abs(time_to_event) < critical_window:
                    return "CRITICAL"
                # High if within 2 hours
                elif abs(time_to_event) < timedelta(hours=2):
                    return "HIGH"
        
        # Moderate if there are news events but not directly affecting pair
        if news_events:
            return "MODERATE"
        
        return "LOW"


# Global instance
news_fetcher = NewsFetcher()
