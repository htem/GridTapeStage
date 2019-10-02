void set_led(byte value) {
  analogWrite(LED, value);
}

void led_on() {
  set_led((byte)0);
}

void led_off() {
  set_led((byte)255);
}

void set_led(CommandProtocol *cmd) {
  if (!cmd->has_arg()) {
    error(ERR_MISSING_ARG);
    return;
  }
  set_led(cmd->get_arg<byte>());
}
