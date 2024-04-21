# SwiftScan

Attendance monitoring tool using NodeMCU ESP8266 and HC-05 Bluetooth Sensor.

## Deploying the Web App

-   Create a `.env` file with the following configs:

    ```env
    MQTT_BROKER_URL=
    MQTT_BROKER_PORT=
    MQTT_USERNAME=
    MQTT_PASSWORD=
    MONGO_URI=
    MAIL_USERNAME=
    MAIL_PASSWORD=
    MAIL_SERVER=
    MAIL_PORT=
    ```

-   Install the requirements:

    ```bash
    pip install -r requirements.txt
    ```

-   Run the flask app:
    ```bash
    python app.py
    ```

**Note:** This application was tested on Python 3.9.16

## Uploading ESP8266 Code

-   Connect your ESP8266 and HC-05 sensor as per the circuit

-   Modify these variables in the `nodemcu_code.ino` accordingly:

    ```c++
    const char* ssid = "<Enter SSID>";
    const char* password = "<Enter WIFI Password>";
    const char* mqtt_server = "MQTT_BROKER_URL";
    const char* mqtt_username = "MQTT_CLIENT_USERNAME";
    const char* mqtt_password = "MQTT_CLIENT_PASSWORD";
    ```

-   In the `PubSubClient.h` header file, modify the following:

    ```c++
    #ifndef MQTT_MAX_PACKET_SIZE
    #define MQTT_MAX_PACKET_SIZE 2000
    #endif
    ```

-   Upload your code

This project was done under the mentorship of Prof. Tarachand Amgoth, students: [@himanshudas75](https://github.com/himanshudas75/), [@imraunn](https://github.com/imraunn/) and [@soumyashree04](https://github.com/soumyashree04/)
