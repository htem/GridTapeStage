interface JavaScript
{
    // Must be defined as global in javascript
    void {{ name }}.joy2d.new_vector(float x, float y);
}

int width = 200;
int height = 200;
int mid_x, mid_y;
float loc_x = 0.;
float loc_y = 0.;
int target_x, target_y;
float vx, vy;
int mouse_down = false;
int cursor_radius = 5;
int loc_radius = 5;
float[][] triangles;

// Setup the Processing Canvas
void setup(){
  size( width, height );
  mid_x = width / 2;
  mid_y = height / 2;

  // build triangles
  triangles = new float[4][6];
  float b = min(width / 5., height / 5.);
  float h = sqrt(3.) * b / 2.;
  float cx = (float) mid_x;
  float cy = ((float) mid_y) / 2.;
  triangles[0][0] = cx - b / 2.;
  triangles[0][1] = cy + h / 2.;
  triangles[0][2] = cx;
  triangles[0][3] = cy - h / 2.;
  triangles[0][4] = cx + b / 2.;
  triangles[0][5] = cy + h / 2.;
  float cx = mid_x * 1.5;
  float cy = mid_y;
  triangles[1][0] = cx - h / 2.;
  triangles[1][1] = cy - b / 2.;
  triangles[1][2] = cx + h / 2.;
  triangles[1][3] = cy;
  triangles[1][4] = cx - h / 2.;
  triangles[1][5] = cy + b / 2.;
  float cx = mid_x;
  float cy = mid_y * 1.5;
  triangles[2][0] = cx + b / 2.;
  triangles[2][1] = cy - h / 2.;
  triangles[2][2] = cx;
  triangles[2][3] = cy + h / 2.;
  triangles[2][4] = cx - b / 2.;
  triangles[2][5] = cy - h / 2.;
  float cx = mid_x / 2.;
  float cy = mid_y;
  triangles[3][0] = cx + h / 2.;
  triangles[3][1] = cy + b / 2.;
  triangles[3][2] = cx - h / 2.;
  triangles[3][3] = cy;
  triangles[3][4] = cx + h / 2.;
  triangles[3][5] = cy - b / 2.;

  strokeWeight( 2 );
  frameRate( 10 );
}

void move_constrained() {
  vx = target_x / width - 0.5;
  vy = target_y / -height + 0.5;
  if (abs(vx) > abs(vy)) {
    vy = 0.;
    target_y = mid_y;
  } else {
    vx = 0.;
    target_x = mid_x;
  }
}

void move_cardinal() {
  vx = target_x / width - 0.5;
  vy = target_y / -height + 0.5;
  if (abs(vx) > abs(vy)) {
    vy = 0.;
    target_y = mid_y;
    if (vx > 0) {
      vx = 0.5;
      target_x = width;
    } else {
      vx = -0.5;
      target_x = 0;
    }
  } else {
    vx = 0.;
    target_x = mid_x;
    if (vy > 0) {
      vy = 0.5;
      target_y = 0;
    } else {
      vy = -0.5;
      target_y = height;
    }
  }
}
 

void move_vector() {
  vx = target_x / width - 0.5;
  vy = target_y / -height + 0.5;
}

void draw_triangles() {
  for (int i = 0; i < 4; i++) {
    triangle(
      triangles[i][0], triangles[i][1],
      triangles[i][2], triangles[i][3],
      triangles[i][4], triangles[i][5]);
  };
}

// Main draw loop
void draw(){
 


  // fill canvas grey
  background( 100 );
  // set fill to grey
  fill(100);
  stroke(75);
  draw_triangles();
  line(0, 0, width, height);
  line(0, height, width, 0);

  // draw central cursor
  stroke(255); 
  ellipse(mid_x, mid_y, cursor_radius, cursor_radius);

  // draw location
  if ((abs(loc_x) == 0.5) | (abs(loc_y) == 0.5)) {
    stroke(255, 0, 0);
    fill(255, 0, 0);
  } else {
    stroke(0, 255, 0);
    fill(0, 255, 0.);
  };
  ellipse((loc_x + 0.5) * width, (-loc_y + 0.5) * height, loc_radius, loc_radius);
  fill(100);

  stroke(255);
  // if mouse is down
  if (mouse_down) {
    if (keyPressed) {
      if (keyCode == SHIFT) {
        move_constrained();
      } else if (keyCode == CONTROL) {
        move_vector();
      } else {
        move_cardinal();
      }
    } else {
      move_cardinal();
    }
    //println("joy2d: vx = " + vx + ", vy = " + vy);
    {{ name }}.joy2d.new_vector((float) vx, (float) vy);

    // draw vector
    line(mid_x, mid_y, target_x, target_y);

    // draw x & y components
    stroke(255, 0, 0, 64);
    line(mid_x, mid_y, target_x, mid_y);
    line(mid_x, target_y, target_x, target_y);
    stroke(0, 0, 255, 64);
    line(mid_x, mid_y, mid_x, target_y);
    line(target_x, mid_y, target_x, target_y);

    // send commands TODO
  };
}

void mouseDragged() {
  if (mouse_down) {
    target_x = mouseX;
    target_y = mouseY;
  }
}

void mouseOut() {
  mouse_down = false;
}

void mousePressed() {
  target_x = mouseX;
  target_y = mouseY;
  mouse_down = true;
}

void mouseReleased() {
  mouse_down = false;
}

void set_location(float x, float y) {
  //println("joy2d: x = " + x + ", y = " + y);
  loc_x = x;
  loc_y = y;
}
