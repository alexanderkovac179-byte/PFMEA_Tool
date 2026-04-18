from app.pipeline import run_fmea_pipeline


def main():
    print("Spúšťam pipeline...")

    try:
        result = run_fmea_pipeline(status_callback=print)
    except Exception as e:
        print(f"Chyba: {e}")
        return

    print(f"Načítaných dokumentov: {result['stats']['documents_count']}")
    print(f"Identifikovaných krokov: {result['stats']['steps_count']}")
    print(f"Názov procesu: {result['metadata']['nazov_procesu']}")
    print(f"Položiek po validácii: {result['stats']['items_after_validation']}")
    print(f"Excel bol uložený do: {result['output_file']}")


if __name__ == "__main__":
    main()