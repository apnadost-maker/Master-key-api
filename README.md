# Key-generate


 if not user_id or not key:
        #temp
        return jsonify({"status": "success"}), 400

    print(f"Check request for user: {user_id}")

    # Check if key is valid (local storage से)
    keys_data = get_keys_from_storage()
    user_data = keys_data.get(user_id)

    if user_data and user_data["key"] == key:
        # Check if key is expired
        expiry_time = datetime.fromisoformat(user_data["expiry_time"])
        current_time = get_current_ist_time()

        if current_time <= expiry_time:
            print(f"Key valid for user: {user_id}")
            return jsonify({"status": "success"})
        else:
            print(f"Key expired for user: {user_id}")
            #temp
            return jsonify({"status": "success"}), 401
    else:
        print(f"Invalid key for user: {user_id}")
        #temp
        return jsonify({"status": "success"}), 401
