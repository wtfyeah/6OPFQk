import requests

API_KEY = "YOUR_API_KEY_HERE"  # put your /api key here
BASE_URL = "https://api.donutsmp.net/v1/stats"

def get_player_stats(username):
    headers = {
        "Authorization": f"Bearer {API_KEY}"
    }

    url = f"{BASE_URL}/{username}"
    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        data = response.json()
        stats = data.get("result", {})

        print(f"\nstats for {username}:")
        for key, value in stats.items():
            print(f"{key}: {value}")

    elif response.status_code == 401:
        print("unauthorized: check your api key")

    elif response.status_code == 500:
        print("error: player may not exist or server failed")

    else:
        print(f"unexpected error: {response.status_code}")
        print(response.text)


if __name__ == "__main__":
    username = input("enter minecraft username: ").strip()
    get_player_stats(username)
