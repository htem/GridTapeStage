void ping(CommandProtocol *cmd) {
  byte v = 0;
  if (cmd->has_arg()) {
    v = cmd->get_arg<byte>();
  }
  cmd->start_command(CMD_PING);
  cmd->add_arg(v);
  cmd->finish_command();
}

void error(byte code) {
  cmd.start_command(CMD_ERROR);
  cmd.add_arg(code);
  cmd.finish_command();
}

void error() {
  error(ERR_ERROR);
}

void configure_drive(dSPIN drive) {
  drive.resetDev();
  drive.configSyncPin(BUSY, 0);
  drive.configStepMode(STEP_FS_128);
  drive.setMaxSpeed(1024);
  drive.setFullSpeed(10000);
  drive.setAcc(16);
  drive.setDec(512);
  drive.setSlewRate(SR_530V_us);
  drive.setOCThreshold(OC_1125mA);
  drive.setPWMFreq(PWM_DIV_2, PWM_MUL_2);
  drive.setOCShutdown(OC_SD_DISABLE);
  drive.setSwitchMode(SW_USER);
  drive.setOscMode(INT_16MHZ_OSCOUT_16MHZ);
  drive.setAccKVAL(RUN_KV);
  drive.setDecKVAL(RUN_KV);
  drive.setRunKVAL(RUN_KV);
  drive.setHoldKVAL(HOLD_KV);
  drive.setLoSpdOpt(true);
  drive.setVoltageComp(VS_COMP_DISABLE);
}

void configure_reel_drive(dSPIN drive) {
  configure_drive(drive);
  drive.setStallThreshold(15);  // empirical
  drive.setOCThreshold(OC_1125mA);
  drive.setOCShutdown(OC_SD_DISABLE);
  drive.setAccKVAL(RUN_KV_REEL);
  drive.setDecKVAL(RUN_KV_REEL);
  drive.setRunKVAL(RUN_KV_REEL);
  drive.setHoldKVAL(HOLD_KV);
  drive.setAcc(512);
  drive.setDec(512);
}

void configure_pinch_drive(dSPIN drive) {
  configure_drive(drive);
  drive.setStallThreshold(15);  // empirical
  drive.setOCThreshold(OC_1125mA);
  drive.setOCShutdown(OC_SD_DISABLE);
  drive.setAccKVAL(RUN_KV_PINCH);
  drive.setDecKVAL(RUN_KV_PINCH);
  drive.setRunKVAL(RUN_KV_PINCH);
  drive.setHoldKVAL(HOLD_KV);
}

void configure_drives() {
  configure_reel_drive(reels);
  configure_pinch_drive(pinches);
}

void reset_drives() {
  configure_drives();
}

void reset_drives(CommandProtocol *cmd) {
  reset_drives();
}

void get_busy(CommandProtocol *cmd) {
  byte r;
  if (cmd->has_arg()) {
    byte drive = cmd->get_arg<byte>();
    switch (drive) {
      case FEED_REEL:
        r = reels.getBusy(FEED);
        break;
      case FEED_PINCH:
        r = pinches.getBusy(FEED);
        break;
      case PICKUP_REEL:
        r = reels.getBusy(PICKUP);
        break;
      case PICKUP_PINCH:
        r = pinches.getBusy(PICKUP);
        break;
      default:
        error(ERR_INVALID_DRIVE);
        r -= 1;
    }
  } else {
    if (digitalRead(BUSY) == HIGH) {
      r = 0;
    } else {
      r = 1;
    }
  }
  // all busy pins are connected
  cmd->start_command(CMD_GET_BUSY);
  cmd->add_arg(r);
  cmd->finish_command();
}

void get_status(CommandProtocol *cmd) {
  if (!cmd->has_arg()) {
    error(ERR_MISSING_ARG);
    return;
  }
  // check type, check side
  int r = 0;
  switch (cmd->get_arg<byte>()) {
    case FEED_REEL:
      r = reels.getStatus(FEED);
      break;
    case FEED_PINCH:
      r = pinches.getStatus(FEED);
      break;
    case PICKUP_REEL:
      r = reels.getStatus(PICKUP);
      break;
    case PICKUP_PINCH:
      r = pinches.getStatus(PICKUP);
      break;
    default:
      error(ERR_INVALID_DRIVE);
      r -= 1;
  }
  cmd->start_command(CMD_GET_STATUS);
  cmd->add_arg(r);
  cmd->finish_command();
}

void get_position(CommandProtocol *cmd) {
  if (!cmd->has_arg()) {
    error(ERR_MISSING_ARG);
    return;
  }
  // check type, check side
  long r = 0;
  switch (cmd->get_arg<byte>()) {
    case FEED_REEL:
      r = reels.getPos(FEED);
      break;
    case FEED_PINCH:
      r = pinches.getPos(FEED);
      break;
    case PICKUP_REEL:
      r = reels.getPos(PICKUP);
      break;
    case PICKUP_PINCH:
      r = pinches.getPos(PICKUP);
      break;
    default:
      error(ERR_INVALID_DRIVE);
      r -= 1;
  }
  cmd->start_command(CMD_GET_POSITION);
  cmd->add_arg(r);
  cmd->finish_command();
}

void set_position(CommandProtocol *cmd) {
  if (!cmd->has_arg()) {
    error(ERR_MISSING_ARG);
    return;
  }
  // check type, check side
  byte drive = cmd->get_arg<byte>();
  if (!cmd->has_arg()) {
    error(ERR_MISSING_ARG);
    return;
  }
  long pos = cmd->get_arg<long>();
  switch (drive) {
    case FEED_REEL:
      reels.setPos(pos, FEED);
      break;
    case FEED_PINCH:
      pinches.setPos(pos, FEED);
      break;
    case PICKUP_REEL:
      reels.setPos(pos, PICKUP);
      break;
    case PICKUP_PINCH:
      pinches.setPos(pos, PICKUP);
      break;
    default:
      error(ERR_INVALID_DRIVE);
  }
}

void hold_drive(CommandProtocol *cmd) {
  if (!cmd->has_arg()) {
    error(ERR_MISSING_ARG);
    return;
  }
  // check type, check side
  byte drive = cmd->get_arg<byte>();
  switch (drive) {
    case FEED_REEL:
      reels.softStop(FEED);
      break;
    case FEED_PINCH:
      pinches.softStop(FEED);
      break;
    case PICKUP_REEL:
      reels.softStop(PICKUP);
      break;
    case PICKUP_PINCH:
      pinches.softStop(PICKUP);
      break;
    default:
      error(ERR_INVALID_DRIVE);
  }
}

void release_drive(CommandProtocol *cmd) {
  if (!cmd->has_arg()) {
    error(ERR_MISSING_ARG);
    return;
  }
  // check type, check side
  byte drive = cmd->get_arg<byte>();
  switch (drive) {
    case FEED_REEL:
      reels.softHiZ(FEED);
      break;
    case FEED_PINCH:
      pinches.softHiZ(FEED);
      break;
    case PICKUP_REEL:
      reels.softHiZ(PICKUP);
      break;
    case PICKUP_PINCH:
      pinches.softHiZ(PICKUP);
      break;
    default:
      error(ERR_INVALID_DRIVE);
  }
}

void rotate_drive(CommandProtocol *cmd) {
  if (!cmd->has_arg()) {
    error(ERR_MISSING_ARG);
    return;
  }
  // check type, check side
  byte drive = cmd->get_arg<byte>();
  if (!cmd->has_arg()) {
    error(ERR_MISSING_ARG);
    return;
  }
  byte dir = cmd->get_arg<byte>();
  if ((dir != 0) && (dir != 1)) {
    error(ERR_INVALID_ARG);
    return;
  }
  if (!cmd->has_arg()) {
    error(ERR_MISSING_ARG);
    return;
  }
  float speed = cmd->get_arg<float>();
  switch (drive) {
    case FEED_REEL:
      reels.run(dir, speed, FEED);
      break;
    case FEED_PINCH:
      pinches.run(dir, speed, FEED);
      break;
    case PICKUP_REEL:
      reels.run(dir, speed, PICKUP);
      break;
    case PICKUP_PINCH:
      pinches.run(dir, speed, PICKUP);
      break;
    default:
      error(ERR_INVALID_DRIVE);
  }
}

void set_speed(byte drive, float speed) {
  switch (drive) {
    case FEED_REEL:
      reels.setMaxSpeed(speed, FEED);
      break;
    case FEED_PINCH:
      pinches.setMaxSpeed(speed, FEED);
      break;
    case PICKUP_REEL:
      reels.setMaxSpeed(speed, PICKUP);
      break;
    case PICKUP_PINCH:
      pinches.setMaxSpeed(speed, PICKUP);
      break;
    default:
      error(ERR_INVALID_DRIVE);
  }
}

void set_speed(CommandProtocol *cmd) {
  // check type, check side
  if (!cmd->has_arg()) {
    error(ERR_MISSING_ARG);
    return;
  }
  byte drive = cmd->get_arg<byte>();
  if (!cmd->has_arg()) {
    error(ERR_MISSING_ARG);
    return;
  }
  float speed = cmd->get_arg<float>();
  set_speed(drive, speed);
}

void get_speed(CommandProtocol *cmd) {
  if (!cmd->has_arg()) {
    error(ERR_MISSING_ARG);
    return;
  }
  // check type, check side
  float s = 0;
  switch (cmd->get_arg<byte>()) {
    case FEED_REEL:
      s = reels.getMaxSpeed(FEED);
      break;
    case FEED_PINCH:
      s = pinches.getMaxSpeed(FEED);
      break;
    case PICKUP_REEL:
      s = reels.getMaxSpeed(PICKUP);
      break;
    case PICKUP_PINCH:
      s = pinches.getMaxSpeed(PICKUP);
      break;
    default:
      error(ERR_INVALID_DRIVE);
  }
  cmd->start_command(CMD_GET_SPEED);
  cmd->add_arg(s);
  cmd->finish_command();
}

void move_drive(CommandProtocol *cmd) {
  if (!cmd->has_arg()) {
    error(ERR_MISSING_ARG);
    return;
  }
  // check type, check side
  byte drive = cmd->get_arg<byte>();
  if (!cmd->has_arg()) {
    error(ERR_MISSING_ARG);
    return;
  }
  byte dir = cmd->get_arg<byte>();
  if ((dir != 0) && (dir != 1)) {
    error(ERR_INVALID_ARG);
    return;
  }
  if (!cmd->has_arg()) {
    error(ERR_MISSING_ARG);
    return;
  }
  unsigned long n_steps = cmd->get_arg<unsigned long>();
  switch (drive) {
    case FEED_REEL:
      reels.move(dir, n_steps, FEED);
      break;
    case FEED_PINCH:
      pinches.move(dir, n_steps, FEED);
      break;
    case PICKUP_REEL:
      reels.move(dir, n_steps, PICKUP);
      break;
    case PICKUP_PINCH:
      pinches.move(dir, n_steps, PICKUP);
      break;
    default:
      error(ERR_INVALID_DRIVE);
  }
}

void run_reels(float speed) {
  reels.run(1, speed, FEED);
  reels.run(0, speed, PICKUP);
}

void run_reels(CommandProtocol *cmd) {
  if (!cmd->has_arg()) {
    error(ERR_MISSING_ARG);
    return;
  }
  float speed = cmd->get_arg<float>();
  run_reels(speed);
}

void stop_reels() {
  reels.softHiZ();
}

void stop_reels(CommandProtocol *cmd) {
  stop_reels();
}

void stop_all(CommandProtocol *cmd) {
  reels.softHiZ();
  pinches.softStop();
}

void release_all() {
  reels.softHiZ();
  pinches.softHiZ();
}

void release_all(CommandProtocol *cmd) {
  release_all();
}

void halt_all() {
  reels.hardHiZ();
  pinches.hardHiZ();
}

void halt_all(CommandProtocol *cmd) {
  halt_all();
}

void wait_for_pinch_drives() {
  while(pinches.getBusy());
  return;
}

byte wait_for_pinch_drives_and_watch_tension(long *tension) {
  long t = 0;
  while(pinches.getBusy()) {
    t = read_tension();
    if ((t > tension_high_limit) | (t < tension_low_limit)) {
      error(ERR_TENSION);
      halt_all();
      *tension = t;
      return 1;
    }
  }
  *tension = t;
  return 0;
}

void step_tape(CommandProtocol *cmd) {
  if (!cmd->has_arg()) {
    error(ERR_MISSING_ARG);
    return;
  }
  byte dir = cmd->get_arg<byte>();
  if (dir > 3) {
    error(ERR_INVALID_ARG);
    return;
  }
  if (!cmd->has_arg()) {
    error(ERR_MISSING_ARG);
    return;
  }
  unsigned long f_steps = cmd->get_arg<unsigned long>();
  if (!cmd->has_arg()) {
    error(ERR_MISSING_ARG);
    return;
  }
  unsigned long p_steps = cmd->get_arg<unsigned long>();
  if (!cmd->has_arg()) {
    error(ERR_MISSING_ARG);
    return;
  }
  float t = cmd->get_arg<float>();
  if (!cmd->has_arg()) {
    error(ERR_MISSING_ARG);
    return;
  }
  byte opts = cmd->get_arg<byte>();
  // set speeds
  set_speed(FEED_PINCH, f_steps / t / 128.);
  set_speed(PICKUP_PINCH, p_steps / t / 128.);
  // start reel drives
  if (opts & ST_OPTS_RUN_REELS) {
    // float max_steps_per_second = max(l_steps / t, r_steps / t);
    // float mm_per_second = max_steps_per_second * PINCH_MM_PER_USTEP;
    // float reel_rpm = mm_per_second * 60. / REEL_MM_PER_REV;
    float reel_rpm = (max(f_steps, p_steps) / t * PINCH_MM_PER_USTEP * 60.) / REEL_MM_PER_REV;
    if (reel_rpm < 1.) {
      reel_rpm = 1.;
    } else {
      reel_rpm += 0.5;
    };
    // convert rpm to steps_per_second
    run_reels(reel_rpm * 200 / 60.);
  };
  switch (dir) {
    case COLLECT: // 0
      pinches.move(COLLECT, p_steps, PICKUP);
      pinches.move(COLLECT, f_steps, FEED);
      break;
    case DISPENSE:
      pinches.move(DISPENSE, f_steps, FEED);
      pinches.move(DISPENSE, p_steps, PICKUP);
      break;
    case TENSION:
      pinches.move(COLLECT, f_steps, FEED);
      pinches.move(DISPENSE, p_steps, PICKUP);
      break;
    case UNTENSION:
      pinches.move(DISPENSE, f_steps, FEED);
      pinches.move(COLLECT, p_steps, PICKUP);
      break;
    default:
      error(ERR_INVALID_DIRECTION);
      return;
  }
  // check if opts said wait
  if (opts & ST_OPTS_WAIT) {
    if (opts & ST_OPTS_WATCH) {
      long t = 0;
      byte err = wait_for_pinch_drives_and_watch_tension(&t);
      if (err != 0) {
        return;
      }
      if (opts & ST_OPTS_RUN_REELS) {
        stop_reels();
      }
      // report finished
      cmd->start_command(CMD_STEP_TAPE);
      cmd->add_arg(t);
      cmd->finish_command();
    } else {
      wait_for_pinch_drives();
      if (opts & ST_OPTS_RUN_REELS) {
        stop_reels();
      }
      cmd->start_command(CMD_STEP_TAPE);
      cmd->add_arg(read_tension());
      cmd->finish_command();
    }
  }
}
