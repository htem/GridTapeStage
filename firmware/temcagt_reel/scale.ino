long read_tension() {
  return scale.read();
}

long read_tension(byte n) {
  return scale.read_average(n);
}

void read_tension(CommandProtocol *cmd) {
  long r;
  if (cmd->has_arg()) {
    byte n = cmd->get_arg<byte>();
    r = scale.read_average(n);
  } else {
    r = scale.read();
  }
  cmd->start_command(CMD_READ_TENSION);
  cmd->add_arg(r);  // long
  cmd->finish_command();
}

void set_tension_limits(CommandProtocol *cmd) {
  if (!cmd->has_arg()) {
    error(ERR_MISSING_ARG);
    return;
  }
  tension_low_limit = cmd->get_arg<long>();
  if (!cmd->has_arg()) {
    error(ERR_MISSING_ARG);
    return;
  }
  tension_high_limit = cmd->get_arg<long>();
}

void get_tension_limits(CommandProtocol *cmd) {
  cmd->start_command(CMD_GET_TENSION_LIMITS);
  cmd->add_arg(tension_low_limit);
  cmd->add_arg(tension_high_limit);
  cmd->finish_command();
}
