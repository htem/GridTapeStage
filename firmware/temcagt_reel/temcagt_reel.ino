/*
 * Temcagt reel control
 * 2015/11/16 : Brett Graham
 *
 * One arduino to control the reel-to-reel mechanism including
 * - tension measurement (HX711)
 * - 2x pinch drive control (dSPIN)
 * - 2x reel drive control (dSPIN)
 *
 * Make this just as 'dumb' as possible
 *
 * Dumbest is:
 * - read tension
 * - move pinch drive [i] by [x]
 * - rotate reel drive [i] at [rpm]
 * - set led
 *
 * A little smarter is
 * - {all above}
 * - set tension low limit [v]
 * - set tension limit high [v]
 * - move pinch drives by [x] watching tension
 * - read moved distance (from eeprom)
 * - write moved distance (to eeprom)
 */

#include <comando.h>
#include "HX711.h"
#include <SPI.h>
#include <dSPIN.h>

#define RUN_KV_PINCH 128
#define RUN_KV_REEL 64
#define RUN_KV 64
#define HOLD_KV 16

#define PINCH_MM_PER_USTEP 0.002734375
#define REEL_MM_PER_REV 120.0

// reel motor 2xdspin board chip select
#define R_SELECT 2
// pinch motor 2xdspin board chip select
#define P_SELECT A2
#define MOSI 11
#define MISO 12
#define SCK 13
#define RESET 4
#define BUSY A5
#define FLAG A4

#define SCALE_DOUT A0
#define SCALE_SCK A1

#define LED 3

// numbered with 0 at the END of the chain, so ST2 = 0, ST1 = 1
#define PICKUP 1
#define FEED 0

#define COLLECT 0
#define DISPENSE 1
#define TENSION 2
#define UNTENSION 3

#define FEED_REEL    B00000000
#define FEED_PINCH   B00000001
#define PICKUP_REEL  B00000010
#define PICKUP_PINCH B00000011

#define CMD_ERROR 0  // -> error_code [byte]
#define CMD_PING 1 // (value [byte]) -> (value [byte])

#define CMD_READ_TENSION 5  // (n_samples [byte]) -> tension [long]
#define CMD_SET_LED 6  // value [byte]

#define CMD_RESET_DRIVES 10
#define CMD_GET_BUSY 11  // (drive [byte]) -> busy [byte]
#define CMD_GET_STATUS 12  // drive [byte] -> status [int]
#define CMD_GET_POSITION 13  // drive [byte] -> position [long]
#define CMD_SET_POSITION 14  // drive [byte], position [long]
#define CMD_HOLD_DRIVE 15  // drive [byte]
#define CMD_RELEASE_DRIVE 16 // drive [byte]
#define CMD_ROTATE_DRIVE 17  // drive [byte], dir [byte], speed [float]
#define CMD_SET_SPEED 18  // drive [byte], speed [float]
#define CMD_GET_SPEED 19  // drive [byte] -> speed [float]
#define CMD_MOVE_DRIVE 20  // drive [byte], dir [byte], n_steps [ulong]

#define CMD_RUN_REELS 21
#define CMD_STOP_REELS 22
#define CMD_STOP_ALL 23
#define CMD_RELEASE_ALL 24
#define CMD_HALT_ALL 25

// dir [byte], f_steps [ulong], p_steps [ulong], time [float], opts [byte] -> []
#define CMD_STEP_TAPE 30
// low [long], high [long]
#define CMD_SET_TENSION_LIMITS 31
// -> low [long], high [long]
#define CMD_GET_TENSION_LIMITS 32

#define ST_OPTS_RUN_REELS 0x01
#define ST_OPTS_WAIT 0x02
#define ST_OPTS_WATCH 0x04

#define ERR_ERROR 0
#define ERR_INVALID_CMD 1
#define ERR_MISSING_ARG 1
#define ERR_INVALID_ARG 2
#define ERR_INVALID_DRIVE 10
#define ERR_INVALID_DIRECTION 11
#define ERR_TENSION 20

// comando
Comando com = Comando(Serial);
EchoProtocol echo = EchoProtocol(com);
CommandProtocol cmd = CommandProtocol(com);

// scale
long tension_low_limit = 8460000;
long tension_high_limit = 8470000;
HX711 scale(SCALE_DOUT, SCALE_SCK);

// reel and pinch motors
dSPIN reels(R_SELECT, RESET, BUSY);
dSPIN pinches(P_SELECT, RESET, BUSY);


void setup() {
  // setup led pin
  pinMode(LED, OUTPUT);
  led_off();
  
  // connect to Serial
  Serial.begin(115200);
  com.register_protocol(0, echo);
  com.register_protocol(1, cmd);
  
  // connect to dspin boards [4]
  configure_drives();
  
  // connect to hx711
 
  // register callbacks
  cmd.register_callback(CMD_PING, ping);
  
  cmd.register_callback(CMD_READ_TENSION, read_tension);
  cmd.register_callback(CMD_SET_LED, set_led);

  cmd.register_callback(CMD_RESET_DRIVES, reset_drives);
  cmd.register_callback(CMD_GET_BUSY, get_busy);
  cmd.register_callback(CMD_GET_STATUS, get_status);
  cmd.register_callback(CMD_GET_POSITION, get_position);
  cmd.register_callback(CMD_SET_POSITION, set_position);
  cmd.register_callback(CMD_HOLD_DRIVE, hold_drive);
  cmd.register_callback(CMD_RELEASE_DRIVE, release_drive);
  cmd.register_callback(CMD_ROTATE_DRIVE, rotate_drive);
  cmd.register_callback(CMD_SET_SPEED, set_speed);
  cmd.register_callback(CMD_GET_SPEED, get_speed);
  cmd.register_callback(CMD_MOVE_DRIVE, move_drive);

  cmd.register_callback(CMD_RUN_REELS, run_reels);
  cmd.register_callback(CMD_STOP_REELS, stop_reels);
  cmd.register_callback(CMD_STOP_ALL, stop_all);
  cmd.register_callback(CMD_RELEASE_ALL, release_all);
  cmd.register_callback(CMD_HALT_ALL, halt_all);
  
  cmd.register_callback(CMD_STEP_TAPE, step_tape);
  cmd.register_callback(CMD_SET_TENSION_LIMITS, set_tension_limits);
  cmd.register_callback(CMD_GET_TENSION_LIMITS, get_tension_limits);
}


void loop() {
  com.handle_stream();
}
