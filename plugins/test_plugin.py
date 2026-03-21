def run():
    print("[PLUGIN] test_plugin is running!")
    # You can also do more: for example, write a file or call the C2 result endpoint
    try:
        with open("plugin_test_output.txt", "w") as f:
            f.write("Plugin executed successfully!\n")
    except Exception as e:
        print(f"[PLUGIN] Error writing output: {e}")