#include <SoftwareSerial.h>
#include <regex.h>
#include <ESP8266WiFi.h>
#include <PubSubClient.h>

#define rx D6
#define tx D5
#define en D7
// #define buzz D2

#define MAX_DEVICES 9
#define WAITING_TIME 5
#define REGEX ".*(OK|ERROR:\\([0-9A-Za-z]+\\))\r\n"

// #undef MQTT_MAX_MESSAGE_SIZE
// #define MQTT_MAX_MESSAGE_SIZE 2000

SoftwareSerial BT(rx, tx);
const char* command_list[] = {
  "AT+RESET\r\n",
  "AT+INIT\r\n",
  "AT+ORGL\r\n",
  "AT+ROLE=1\r\n",
  "AT+INQM=0,9,5\r\n",
};

bool initial_setup = true;
bool active = false;

const char* ssid = "<Enter SSID>";
const char* password = "<Enter WIFI Password>";

const char* mqtt_server = "MQTT_BROKER_URL";
const char* mqtt_username = "MQTT_CLIENT_USERNAME";
const char* mqtt_password = "MQTT_CLIENT_PASSWORD";
const int mqtt_port = 8883;

const char *clientId = "NodeMCU_Blue";
const char* recv_topic = "blue_config";
const char* send_topic = "blue_attendance";

WiFiClientSecure espClient;
PubSubClient client(espClient);

void serialFlush() {
  while (Serial.available() > 0) {
    char t = Serial.read();
  }
}

void BTFlush() {
  while (BT.available() > 0) {
    char t = BT.read();
  }
}

char* stringToHex(char *input) {
    int input_length = strlen(input), i, j;
    char *output = (char*)malloc(2 * input_length + 1);

    for (i = 0, j = 0; i < input_length; i++, j += 2) {
        sprintf((char*)output + j, "%02X", input[i]);
    }
    output[j] = '\0';

    return output;
}

int match_regex(char *str) {
  regex_t regex;
  int ret;

  ret = regcomp(&regex, REGEX, REG_EXTENDED | REG_NEWLINE);
  ret = regexec(&regex, str, 0, NULL, 0);

  regfree(&regex);

  return (ret == 0) ? 1 : 0;
}

char* read_output() {
  char *buffer = NULL;
  int buffer_size = 0;

  int counter=0;
  while (1) {
    if (BT.available()) {
      counter=0;
      char x = BT.read();
      Serial.print(x);
      buffer = (char*)realloc(buffer, buffer_size + 2);
      buffer[buffer_size] = x;
      buffer[buffer_size + 1] = '\0';
      buffer_size += 1;

      if(buffer_size >= 4){
        if(memcmp(buffer + buffer_size - 4, "OK\r\n", 4) == 0)
          break;
        else if(memcmp(buffer + buffer_size - 3, ")\r\n", 3) == 0){
          free(buffer);
          buffer = NULL;
          break;
        }
      }

    }
    else {
      counter+=1;
      delay(10);
      if(counter==1000){
        if(buffer != NULL){
          free(buffer);
          buffer = NULL;
        }
        break;
      }
    }
  }

    // int ret = match_regex(buffer);
    // if (ret == 1) {
    //   return buffer;
    // }
    // else{
    //   if(buffer != NULL)
    //     free(buffer);
    //   return NULL;
    // }
    return buffer;
}

char* send_command(const char *command) {
  delay(1000);
  BT.write(command);
  delay(1000);
  char* ret = read_output();
  delay(1000);
  return ret;
}

void reconnect() {
  while (!client.connected()) {
    Serial.print("Attempting MQTT connection...");
    if (client.connect(clientId, mqtt_username, mqtt_password)) {
      Serial.println("connected");
      client.subscribe(recv_topic);

    } else {
      Serial.print("failed, rc=");
      Serial.print(client.state());
      Serial.println(" try again in 5 seconds");
      delay(5000);
    }
  }
}

void publishMessage(char* payload , boolean retained){
  Serial.println(F("SENDING MESSAGE..."));
  if (!client.connected())
    reconnect();
  if (client.publish(send_topic, payload, retained))
    Serial.println(F("MESSAGE SENT..."));
  else
    Serial.println(F("ERROR SENDING MESSAGE"));
}


void send_attendance(char *input) {
  
  if(WiFi.status() == WL_CONNECTED) {
      char *hexified = stringToHex(input);
      publishMessage(hexified, false);
      delay(5000);
      free(hexified);
    }
    else {
      Serial.println(F("WiFi Disconnected"));
    }
    
}

void callback(char* topic, byte* payload, unsigned int length) {
  char message[length+1];

  for (int i = 0; i < length; i++)
    message[i]=(char)payload[i];
  message[length] = '\0';

  Serial.print("RECEIVED: ");
  Serial.println(message);

  if(strcmp(message, "START") == 0){
    Serial.println(F("STARTING IOT..."));
    active = true;
  }

  else if(strcmp(message, "STOP") == 0){
    Serial.println(F("TERMINATING IOT..."));
    active = false;
  }

  else{
    Serial.println(F("UNKNOWN MESSAGE..."));
  }
}

void setup() {
  pinMode(en, OUTPUT);
  digitalWrite(en, HIGH);

  // pinMode(buzz, OUTPUT);

  BT.begin(38400);
  Serial.begin(9600);

  // Setup Wifi
  WiFi.begin(ssid, password);
  Serial.println(F("Connecting"));
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("");
  Serial.print(F("Connected to WiFi network with IP Address: "));
  Serial.println(WiFi.localIP());

  delay(1000);

  // Set up MQTT
  espClient.setInsecure();
  client.setServer(mqtt_server, mqtt_port);
  client.setCallback(callback);

  delay(1000);

}

void loop() {
  if (!client.connected())
    reconnect();
  client.loop();

  if (initial_setup) {
    Serial.println(F("INIT"));
    serialFlush();
    BTFlush();

    int length = sizeof(command_list) / sizeof(command_list[0]);

    for (int i = 0; i < length; i++)
      send_command(command_list[i]);

    Serial.println(F("INIT DONE"));
    initial_setup = false;

    // digitalWrite(buzz, HIGH);
    // delay(500);
    // digitalWrite(buzz, LOW);
  }
  
  

  if(active){
    delay(3000);
    Serial.println(F("SEARCHING FOR DEVICES"));

    char* output = send_command("AT+INQ\r\n");
    if(output != NULL){
      send_attendance(output);
      free(output);
    }

    Serial.println(F("SEARCHING DONE"));
  }
}