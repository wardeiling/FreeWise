"""
Quick test to verify review session streak calculation logic.
"""
from datetime import date, timedelta

def calculate_streaks(session_dates):
    """Test the streak calculation logic."""
    if not session_dates:
        return 0, 0
    
    # Sort dates
    sorted_dates = sorted(session_dates, reverse=True)
    
    # Calculate current streak
    current_streak = 0
    today_date = date.today()
    yesterday = today_date - timedelta(days=1)
    
    # Check if there's a session today or yesterday to start the streak
    if sorted_dates[0] >= yesterday:
        current_streak = 1
        check_date = sorted_dates[0] - timedelta(days=1)
        
        for i in range(1, len(sorted_dates)):
            if sorted_dates[i] == check_date:
                current_streak += 1
                check_date -= timedelta(days=1)
            elif sorted_dates[i] < check_date:
                # Gap found, break
                break
    
    # Calculate longest streak
    all_dates_sorted = sorted(session_dates)
    temp_streak = 1
    longest_streak = 1
    
    for i in range(1, len(all_dates_sorted)):
        days_diff = (all_dates_sorted[i] - all_dates_sorted[i-1]).days
        if days_diff == 1:
            temp_streak += 1
            longest_streak = max(longest_streak, temp_streak)
        else:
            temp_streak = 1
    
    return current_streak, longest_streak

# Test cases
print("Test Case 1: Review every day for 5 days (including today)")
today = date.today()
test1 = [today - timedelta(days=i) for i in range(5)]
current, longest = calculate_streaks(test1)
print(f"  Current: {current}, Longest: {longest}")
print(f"  Expected: Current: 5, Longest: 5")
print()

print("Test Case 2: Review for 3 days, skip 2, review for 5 days (ending today)")
test2 = [today - timedelta(days=i) for i in range(5)]  # Last 5 days
test2.extend([today - timedelta(days=i) for i in range(7, 10)])  # 3 more earlier
current, longest = calculate_streaks(test2)
print(f"  Current: {current}, Longest: {longest}")
print(f"  Expected: Current: 5, Longest: 5")
print()

print("Test Case 3: No review today, but reviewed yesterday and day before")
test3 = [today - timedelta(days=1), today - timedelta(days=2)]
current, longest = calculate_streaks(test3)
print(f"  Current: {current}, Longest: {longest}")
print(f"  Expected: Current: 2, Longest: 2")
print()

print("Test Case 4: Long streak in the past, but nothing recent")
test4 = [today - timedelta(days=10 + i) for i in range(7)]
current, longest = calculate_streaks(test4)
print(f"  Current: {current}, Longest: {longest}")
print(f"  Expected: Current: 0, Longest: 7")
print()

print("Test Case 5: Single review today")
test5 = [today]
current, longest = calculate_streaks(test5)
print(f"  Current: {current}, Longest: {longest}")
print(f"  Expected: Current: 1, Longest: 1")
